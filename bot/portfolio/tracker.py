"""Portfolio tracking and PnL calculation."""

import logging
from datetime import datetime, timedelta

from bot.database.db import get_session
from bot.database.models import Position, Trade, PortfolioSnapshot

logger = logging.getLogger(__name__)


class PortfolioTracker:
    """Tracks portfolio value, positions, and PnL over time."""

    def __init__(self, exchange_client, is_paper: bool = True):
        self.client = exchange_client
        self.is_paper = is_paper

    def get_summary(self) -> dict:
        """Get a complete portfolio summary."""
        session = get_session()
        try:
            balance = self.client.get_balance()
            total_value = self._calculate_total_value(balance)
            positions = self._get_open_positions(session)
            daily_pnl = self._get_daily_pnl(session)
            total_pnl = self._get_total_pnl(session)

            return {
                "total_value_usdt": total_value,
                "available_usdt": balance.get("USDT", {}).get("free", 0),
                "in_positions": sum(
                    p["current_value"] for p in positions
                ),
                "num_positions": len(positions),
                "positions": positions,
                "daily_pnl": daily_pnl,
                "total_pnl": total_pnl,
                "unrealized_pnl": sum(
                    p["unrealized_pnl"] for p in positions
                ),
                "balances": balance,
                "is_paper": self.is_paper,
            }
        finally:
            session.close()

    def get_open_positions(self) -> list:
        """Get all open positions with current prices and PnL."""
        session = get_session()
        try:
            return self._get_open_positions(session)
        finally:
            session.close()

    def update_positions(self):
        """Update current prices and unrealized PnL for all open positions."""
        session = get_session()
        try:
            positions = session.query(Position).filter_by(is_open=True).all()
            for position in positions:
                try:
                    current_price = self.client.get_price(position.symbol)
                    position.current_price = current_price
                    if position.side == "long":
                        position.unrealized_pnl = (
                            (current_price - position.entry_price) * position.amount
                        )
                    else:
                        position.unrealized_pnl = (
                            (position.entry_price - current_price) * position.amount
                        )
                except Exception as e:
                    logger.error(
                        "Failed to update position %s: %s", position.symbol, e
                    )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to update positions: %s", e)
        finally:
            session.close()

    def take_snapshot(self):
        """Take a portfolio snapshot and save to database."""
        session = get_session()
        try:
            balance = self.client.get_balance()
            total_value = self._calculate_total_value(balance)

            positions = session.query(Position).filter_by(is_open=True).all()
            in_positions = sum(
                (p.current_price or p.entry_price) * p.amount for p in positions
            )
            unrealized = sum(p.unrealized_pnl or 0 for p in positions)
            daily_pnl = self._get_daily_pnl(session)
            total_pnl = self._get_total_pnl(session)

            snapshot = PortfolioSnapshot(
                total_balance=total_value,
                available_balance=balance.get("USDT", {}).get("free", 0),
                in_positions=in_positions,
                total_pnl=total_pnl,
                daily_pnl=daily_pnl,
                unrealized_pnl=unrealized,
                num_open_positions=len(positions),
            )
            session.add(snapshot)
            session.commit()

            logger.info(
                "Snapshot: Balance=%.2f, Positions=%d, Daily PnL=%.2f",
                total_value, len(positions), daily_pnl,
            )
            return snapshot

        except Exception as e:
            session.rollback()
            logger.error("Failed to take snapshot: %s", e)
        finally:
            session.close()

    def get_trade_history(self, limit: int = 50, offset: int = 0) -> list:
        """Get recent trade history."""
        session = get_session()
        try:
            trades = (
                session.query(Trade)
                .order_by(Trade.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "amount": t.amount,
                    "price": t.average_price or t.price,
                    "cost": t.cost,
                    "fee": t.fee,
                    "strategy": t.strategy,
                    "status": t.status,
                    "pnl": t.pnl,
                    "is_paper": t.is_paper,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in trades
            ]
        finally:
            session.close()

    def get_pnl_history(self, days: int = 30) -> list:
        """Get portfolio PnL history from snapshots."""
        session = get_session()
        try:
            since = datetime.utcnow() - timedelta(days=days)
            snapshots = (
                session.query(PortfolioSnapshot)
                .filter(PortfolioSnapshot.timestamp >= since)
                .order_by(PortfolioSnapshot.timestamp.asc())
                .all()
            )
            return [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "total_balance": s.total_balance,
                    "daily_pnl": s.daily_pnl,
                    "total_pnl": s.total_pnl,
                    "unrealized_pnl": s.unrealized_pnl,
                    "num_positions": s.num_open_positions,
                }
                for s in snapshots
            ]
        finally:
            session.close()

    def get_strategy_performance(self) -> dict:
        """Get PnL breakdown by strategy."""
        session = get_session()
        try:
            strategies = ["ai", "copy", "signal", "manual"]
            result = {}
            for strategy in strategies:
                trades = (
                    session.query(Trade)
                    .filter_by(strategy=strategy)
                    .filter(Trade.pnl.isnot(None))
                    .all()
                )
                if trades:
                    total_pnl = sum(t.pnl for t in trades)
                    winners = sum(1 for t in trades if t.pnl > 0)
                    result[strategy] = {
                        "total_trades": len(trades),
                        "total_pnl": total_pnl,
                        "winners": winners,
                        "losers": len(trades) - winners,
                        "win_rate": winners / len(trades) * 100 if trades else 0,
                        "avg_pnl": total_pnl / len(trades) if trades else 0,
                    }
            return result
        finally:
            session.close()

    def _calculate_total_value(self, balance: dict) -> float:
        """Calculate total portfolio value in USDT."""
        total = balance.get("USDT", {}).get("total", 0)
        for currency, amounts in balance.items():
            if currency == "USDT":
                continue
            try:
                price = self.client.get_price(f"{currency}/USDT")
                total += amounts.get("total", 0) * price
            except Exception:
                pass  # Skip currencies we can't price
        return total

    def _get_open_positions(self, session) -> list:
        """Get formatted list of open positions."""
        positions = session.query(Position).filter_by(is_open=True).all()
        result = []
        for p in positions:
            current_value = (p.current_price or p.entry_price) * p.amount
            result.append({
                "id": p.id,
                "symbol": p.symbol,
                "side": p.side,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "amount": p.amount,
                "current_value": current_value,
                "unrealized_pnl": p.unrealized_pnl or 0,
                "unrealized_pnl_pct": (
                    (p.unrealized_pnl / (p.entry_price * p.amount) * 100)
                    if p.unrealized_pnl and p.entry_price * p.amount > 0
                    else 0
                ),
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "strategy": p.strategy,
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
            })
        return result

    def _get_daily_pnl(self, session) -> float:
        """Get today's realized PnL."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        trades = (
            session.query(Trade)
            .filter(Trade.created_at >= today, Trade.pnl.isnot(None))
            .all()
        )
        return sum(t.pnl for t in trades) if trades else 0.0

    def _get_total_pnl(self, session) -> float:
        """Get all-time realized PnL."""
        trades = session.query(Trade).filter(Trade.pnl.isnot(None)).all()
        return sum(t.pnl for t in trades) if trades else 0.0
