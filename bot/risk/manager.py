"""Risk management system - enforces all trading risk rules."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from bot.database.db import get_session
from bot.database.models import Position, Trade, PortfolioSnapshot

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Enforces all risk rules before any trade is executed.
    Every trade from every strategy must pass through pre_trade_check().

    Risk Rules:
    - Max position size (% of portfolio)
    - Max number of concurrent positions
    - Daily loss limit / max drawdown circuit breaker
    - Stop-loss and take-profit calculation
    - Cooldown after consecutive losses
    """

    def __init__(
        self,
        max_position_size_pct: float = 10.0,
        max_positions: int = 5,
        daily_loss_limit_pct: float = 5.0,
        stop_loss_pct: float = 3.0,
        take_profit_pct: float = 6.0,
        trailing_stop_pct: float = 2.0,
        max_drawdown_pct: float = 15.0,
        cooldown_after_losses: int = 3,
        cooldown_minutes: int = 60,
    ):
        self.max_position_size_pct = max_position_size_pct
        self.max_positions = max_positions
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.cooldown_after_losses = cooldown_after_losses
        self.cooldown_minutes = cooldown_minutes

        # Track high-water mark for drawdown calculation
        self._peak_balance = 0.0
        self._consecutive_losses = 0
        self._last_loss_time: Optional[datetime] = None

    def pre_trade_check(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
    ) -> dict:
        """
        Run all risk checks before a trade.

        Returns:
            {
                "allowed": bool,
                "reason": str,
                "adjusted_amount": float,
                "stop_loss": float,
                "take_profit": float,
            }
        """
        session = get_session()
        try:
            # 1. Check cooldown period after consecutive losses
            if self._is_in_cooldown():
                return self._reject(
                    f"Cooldown active: {self.cooldown_after_losses} consecutive losses. "
                    f"Wait {self.cooldown_minutes} minutes."
                )

            # 2. Check daily loss limit
            daily_pnl = self._get_daily_pnl(session)
            if daily_pnl is not None and daily_pnl < 0:
                daily_loss_pct = abs(daily_pnl) / max(self._peak_balance, 1) * 100
                if daily_loss_pct >= self.daily_loss_limit_pct:
                    return self._reject(
                        f"Daily loss limit reached: {daily_loss_pct:.1f}% "
                        f"(limit: {self.daily_loss_limit_pct}%)"
                    )

            # 3. Check max drawdown circuit breaker
            if self._is_max_drawdown_exceeded(session):
                return self._reject(
                    f"Max drawdown exceeded: {self.max_drawdown_pct}%. "
                    "Circuit breaker active. Manual reset required."
                )

            # 4. Check max number of open positions
            open_positions = session.query(Position).filter_by(is_open=True).count()
            if side == "buy" and open_positions >= self.max_positions:
                return self._reject(
                    f"Max positions reached: {open_positions}/{self.max_positions}"
                )

            # 5. Check and adjust position size
            adjusted_amount = self._check_position_size(
                session, symbol, amount, price
            )

            # 6. Check if we already have an open position in this symbol
            existing = session.query(Position).filter_by(
                symbol=symbol, is_open=True
            ).first()
            if existing and side == "buy" and existing.side == "long":
                # Adding to existing position - check combined size
                combined_value = (existing.amount * existing.entry_price) + (adjusted_amount * price)
                max_value = self._get_max_position_value(session)
                if combined_value > max_value:
                    adjusted_amount = max(0, (max_value - existing.amount * existing.entry_price) / price)
                    if adjusted_amount <= 0:
                        return self._reject(
                            f"Position in {symbol} already at max size"
                        )

            # 7. Calculate stop-loss and take-profit
            stop_loss, take_profit = self._calculate_sl_tp(price, side)

            logger.info(
                "Risk check PASSED: %s %s %s (adjusted: %s) SL=%.2f TP=%.2f",
                side, amount, symbol, adjusted_amount, stop_loss, take_profit,
            )

            return {
                "allowed": True,
                "reason": "approved",
                "adjusted_amount": adjusted_amount,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }

        except Exception as e:
            logger.error("Risk check error: %s", e)
            return self._reject(f"Risk check error: {e}")
        finally:
            session.close()

    def post_trade_update(self, trade_pnl: Optional[float] = None):
        """Update internal state after a trade executes."""
        if trade_pnl is not None and trade_pnl < 0:
            self._consecutive_losses += 1
            self._last_loss_time = datetime.utcnow()
            logger.info(
                "Consecutive losses: %d/%d",
                self._consecutive_losses, self.cooldown_after_losses,
            )
        elif trade_pnl is not None and trade_pnl >= 0:
            self._consecutive_losses = 0

    def update_peak_balance(self, current_balance: float):
        """Update the high-water mark for drawdown tracking."""
        if current_balance > self._peak_balance:
            self._peak_balance = current_balance

    def check_stop_loss_take_profit(self, exchange_client) -> list:
        """
        Check all open positions for stop-loss and take-profit triggers.
        Returns list of positions that were closed.
        """
        session = get_session()
        closed = []
        try:
            positions = session.query(Position).filter_by(is_open=True).all()

            for position in positions:
                try:
                    current_price = exchange_client.get_price(position.symbol)
                    position.current_price = current_price

                    # Calculate current unrealized PnL
                    if position.side == "long":
                        position.unrealized_pnl = (
                            (current_price - position.entry_price) * position.amount
                        )
                    else:
                        position.unrealized_pnl = (
                            (position.entry_price - current_price) * position.amount
                        )

                    should_close = False
                    reason = ""

                    # Check stop-loss
                    if position.stop_loss:
                        if position.side == "long" and current_price <= position.stop_loss:
                            should_close = True
                            reason = f"Stop-loss triggered at {current_price}"
                        elif position.side == "short" and current_price >= position.stop_loss:
                            should_close = True
                            reason = f"Stop-loss triggered at {current_price}"

                    # Check take-profit
                    if position.take_profit and not should_close:
                        if position.side == "long" and current_price >= position.take_profit:
                            should_close = True
                            reason = f"Take-profit triggered at {current_price}"
                        elif position.side == "short" and current_price <= position.take_profit:
                            should_close = True
                            reason = f"Take-profit triggered at {current_price}"

                    if should_close:
                        logger.info(
                            "Position %s %s: %s", position.id, position.symbol, reason
                        )
                        closed.append({
                            "position_id": position.id,
                            "symbol": position.symbol,
                            "reason": reason,
                            "current_price": current_price,
                            "unrealized_pnl": position.unrealized_pnl,
                        })

                except Exception as e:
                    logger.error(
                        "Error checking position %s: %s", position.id, e
                    )

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Error in SL/TP check: %s", e)
        finally:
            session.close()

        return closed

    def get_risk_status(self) -> dict:
        """Get current risk metrics."""
        session = get_session()
        try:
            open_positions = session.query(Position).filter_by(is_open=True).count()
            daily_pnl = self._get_daily_pnl(session) or 0
            return {
                "open_positions": open_positions,
                "max_positions": self.max_positions,
                "daily_pnl": daily_pnl,
                "daily_loss_limit_pct": self.daily_loss_limit_pct,
                "peak_balance": self._peak_balance,
                "consecutive_losses": self._consecutive_losses,
                "cooldown_active": self._is_in_cooldown(),
                "max_drawdown_pct": self.max_drawdown_pct,
            }
        finally:
            session.close()

    def _check_position_size(
        self, session, symbol: str, amount: float, price: float
    ) -> float:
        """Adjust position size to respect max position size limit."""
        max_value = self._get_max_position_value(session)
        proposed_value = amount * price

        if proposed_value > max_value:
            adjusted = max_value / price
            logger.info(
                "Position size adjusted: %.4f -> %.4f (max value: %.2f)",
                amount, adjusted, max_value,
            )
            return adjusted
        return amount

    def _get_max_position_value(self, session) -> float:
        """Get max allowed position value in USDT."""
        latest_snapshot = (
            session.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .first()
        )
        total_balance = latest_snapshot.total_balance if latest_snapshot else self._peak_balance
        if total_balance <= 0:
            total_balance = 10000  # Default for initial trading
        return total_balance * (self.max_position_size_pct / 100)

    def _get_daily_pnl(self, session) -> Optional[float]:
        """Get today's total realized PnL."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        trades = (
            session.query(Trade)
            .filter(Trade.created_at >= today, Trade.pnl.isnot(None))
            .all()
        )
        if not trades:
            return 0.0
        return sum(t.pnl for t in trades)

    def _is_max_drawdown_exceeded(self, session) -> bool:
        """Check if max drawdown from peak has been exceeded."""
        if self._peak_balance <= 0:
            return False
        latest = (
            session.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .first()
        )
        if not latest:
            return False
        drawdown = (self._peak_balance - latest.total_balance) / self._peak_balance * 100
        return drawdown >= self.max_drawdown_pct

    def _is_in_cooldown(self) -> bool:
        """Check if we're in a cooldown period after consecutive losses."""
        if self._consecutive_losses < self.cooldown_after_losses:
            return False
        if self._last_loss_time is None:
            return False
        cooldown_end = self._last_loss_time + timedelta(minutes=self.cooldown_minutes)
        if datetime.utcnow() < cooldown_end:
            return True
        # Cooldown expired, reset
        self._consecutive_losses = 0
        return False

    def _calculate_sl_tp(self, price: float, side: str) -> tuple[float, float]:
        """Calculate stop-loss and take-profit prices."""
        if side == "buy":
            stop_loss = price * (1 - self.stop_loss_pct / 100)
            take_profit = price * (1 + self.take_profit_pct / 100)
        else:
            stop_loss = price * (1 + self.stop_loss_pct / 100)
            take_profit = price * (1 - self.take_profit_pct / 100)
        return round(stop_loss, 8), round(take_profit, 8)

    @staticmethod
    def _reject(reason: str) -> dict:
        logger.warning("Trade REJECTED: %s", reason)
        return {
            "allowed": False,
            "reason": reason,
            "adjusted_amount": 0,
            "stop_loss": 0,
            "take_profit": 0,
        }
