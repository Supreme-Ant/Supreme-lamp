"""Copy trading strategy - monitors and replicates trades from top traders."""

import logging
from datetime import datetime
from typing import Optional

from bot.strategies.base import BaseStrategy
from bot.database.db import get_session
from bot.database.models import CopyLeader, Trade

logger = logging.getLogger(__name__)


class CopyTrader(BaseStrategy):
    """
    Monitors top traders and replicates their trades proportionally.

    Copy Trading Workflow:
    1. Poll each active leader's recent trades via exchange API
    2. Detect new trades not yet replicated
    3. Calculate proportional position size based on allocation_pct
    4. Execute trades through risk manager
    5. Track all copied trades with leader reference
    """

    def __init__(
        self,
        order_manager,
        exchange_client,
        risk_manager=None,
        notifier=None,
        trade_ratio: float = 0.1,
        min_trade_usdt: float = 10.0,
    ):
        super().__init__("copy", order_manager, risk_manager, notifier)
        self.exchange = exchange_client
        self.trade_ratio = trade_ratio
        self.min_trade_usdt = min_trade_usdt

        # Cache of seen trade IDs per leader to avoid duplicates
        self._seen_trades: dict[str, set] = {}

    def run(self) -> list:
        """Execute one copy trading cycle - check all leaders for new trades."""
        if not self.is_active:
            return []

        orders = []
        session = get_session()
        try:
            leaders = session.query(CopyLeader).filter_by(is_active=True).all()
            if not leaders:
                return []

            for leader in leaders:
                try:
                    new_orders = self._process_leader(leader, session)
                    orders.extend(new_orders)
                except Exception as e:
                    logger.error(
                        "Error processing leader %s: %s", leader.external_id, e
                    )

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Copy trading cycle error: %s", e)
        finally:
            session.close()

        return orders

    def add_leader(
        self,
        external_id: str,
        label: Optional[str] = None,
        allocation_pct: float = 0.1,
    ) -> CopyLeader:
        """Add a new leader to track."""
        session = get_session()
        try:
            leader = CopyLeader(
                external_id=external_id,
                label=label or external_id,
                allocation_pct=allocation_pct,
                is_active=True,
            )
            session.add(leader)
            session.commit()
            logger.info("Added copy leader: %s (allocation: %.1f%%)", label, allocation_pct * 100)
            return leader
        except Exception as e:
            session.rollback()
            logger.error("Failed to add leader: %s", e)
            raise
        finally:
            session.close()

    def remove_leader(self, external_id: str):
        """Deactivate a leader."""
        session = get_session()
        try:
            leader = session.query(CopyLeader).filter_by(external_id=external_id).first()
            if leader:
                leader.is_active = False
                session.commit()
                logger.info("Deactivated leader: %s", external_id)
        finally:
            session.close()

    def get_leaders(self) -> list:
        """Get all copy trading leaders."""
        session = get_session()
        try:
            leaders = session.query(CopyLeader).all()
            return [
                {
                    "id": l.id,
                    "external_id": l.external_id,
                    "label": l.label,
                    "allocation_pct": l.allocation_pct,
                    "is_active": l.is_active,
                    "total_pnl": l.total_pnl,
                    "num_trades": l.num_trades_copied,
                    "last_polled": l.last_polled_at.isoformat() if l.last_polled_at else None,
                }
                for l in leaders
            ]
        finally:
            session.close()

    def get_status(self) -> dict:
        """Get copy trading strategy status."""
        session = get_session()
        try:
            active_leaders = session.query(CopyLeader).filter_by(is_active=True).count()
            total_copied = (
                session.query(Trade).filter_by(strategy="copy").count()
            )
            total_pnl = sum(
                t.pnl or 0
                for t in session.query(Trade)
                .filter_by(strategy="copy")
                .filter(Trade.pnl.isnot(None))
                .all()
            )
            return {
                "strategy": "copy",
                "is_active": self.is_active,
                "active_leaders": active_leaders,
                "total_trades_copied": total_copied,
                "total_pnl": total_pnl,
                "trade_ratio": self.trade_ratio,
            }
        finally:
            session.close()

    def _process_leader(self, leader: CopyLeader, session) -> list:
        """Check a single leader for new trades and replicate them."""
        orders = []

        # Initialize seen trades set for this leader
        if leader.external_id not in self._seen_trades:
            self._seen_trades[leader.external_id] = set()
            # On first run, load existing copied trades to avoid duplicates
            existing = (
                session.query(Trade)
                .filter_by(strategy="copy", leader_id=leader.external_id)
                .all()
            )
            for t in existing:
                if t.order_id:
                    self._seen_trades[leader.external_id].add(t.order_id)

        # Fetch leader's recent trades
        since = None
        if leader.last_polled_at:
            since = int(leader.last_polled_at.timestamp() * 1000)

        try:
            # This requires the leader's API key to be configured
            # In practice, you'd have a separate exchange client for each leader
            leader_trades = self.exchange.get_my_trades(since=since, limit=50)
        except Exception as e:
            logger.error("Failed to fetch trades for leader %s: %s", leader.external_id, e)
            return orders

        # Filter to new trades only
        for trade in leader_trades:
            trade_id = trade.get("id", "")
            if trade_id in self._seen_trades[leader.external_id]:
                continue

            self._seen_trades[leader.external_id].add(trade_id)

            # Calculate our position size
            our_amount = self._calculate_copy_amount(trade, leader)
            if our_amount <= 0:
                continue

            symbol = trade.get("symbol", "")
            side = trade.get("side", "")

            # Verify minimum trade size
            price = trade.get("price", 0)
            if our_amount * price < self.min_trade_usdt:
                logger.debug(
                    "Skipping copy trade: value %.2f < min %.2f",
                    our_amount * price, self.min_trade_usdt,
                )
                continue

            # Place the copied trade
            order = self._place_order(
                symbol=symbol,
                side=side,
                amount=our_amount,
                leader_id=leader.external_id,
            )

            if order:
                orders.append(order)
                leader.num_trades_copied += 1

                if self.notifier:
                    self.notifier.send(
                        f"📋 COPY TRADE from {leader.label}\n"
                        f"{side.upper()} {our_amount} {symbol}\n"
                        f"Leader traded: {trade.get('amount')} @ {price}"
                    )

        leader.last_polled_at = datetime.utcnow()
        return orders

    def _calculate_copy_amount(self, leader_trade: dict, leader: CopyLeader) -> float:
        """Calculate our position size proportional to the leader's trade."""
        leader_amount = leader_trade.get("amount", 0)
        leader_price = leader_trade.get("price", 0)

        if leader_amount <= 0 or leader_price <= 0:
            return 0

        # Get our available balance
        balance = self.exchange.get_balance()
        available_usdt = balance.get("USDT", {}).get("free", 0)

        # Calculate based on allocation percentage
        allocated_usdt = available_usdt * leader.allocation_pct
        our_amount = allocated_usdt / leader_price

        # Apply trade ratio cap
        max_from_ratio = leader_amount * self.trade_ratio
        our_amount = min(our_amount, max_from_ratio)

        return our_amount
