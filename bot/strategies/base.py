"""Base strategy interface for all trading strategies."""

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Every strategy must implement the run() method.
    """

    def __init__(self, name: str, order_manager, risk_manager=None, notifier=None):
        self.name = name
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.notifier = notifier
        self.is_active = True

    @abstractmethod
    def run(self) -> list:
        """
        Execute one cycle of the strategy.
        Returns a list of orders placed (or empty list).
        """
        pass

    @abstractmethod
    def get_status(self) -> dict:
        """Return current strategy status and metrics."""
        pass

    def start(self):
        """Activate the strategy."""
        self.is_active = True
        logger.info("Strategy '%s' started", self.name)

    def stop(self):
        """Deactivate the strategy."""
        self.is_active = False
        logger.info("Strategy '%s' stopped", self.name)

    def _place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        signal_id: Optional[int] = None,
        leader_id: Optional[str] = None,
    ) -> Optional[dict]:
        """Convenience method to place an order through the order manager."""
        if not self.is_active:
            logger.warning("Strategy '%s' is inactive, skipping order", self.name)
            return None

        return self.order_manager.place_order(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
            strategy=self.name,
            signal_id=signal_id,
            leader_id=leader_id,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
