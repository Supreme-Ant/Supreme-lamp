"""Signal follower strategy - parses and acts on trading signals from Telegram."""

import logging
import re
from typing import Optional

from bot.strategies.base import BaseStrategy
from bot.database.db import get_session
from bot.database.models import Signal

logger = logging.getLogger(__name__)


# Common signal patterns from Telegram channels
SIGNAL_PATTERNS = [
    # Pattern: "BUY BTC/USDT @ 50000 SL: 48000 TP: 55000"
    re.compile(
        r"(?P<action>BUY|SELL)\s+(?P<symbol>\w+/\w+)\s*@?\s*(?P<price>[\d.]+)"
        r"(?:.*?SL[:\s]+(?P<sl>[\d.]+))?"
        r"(?:.*?TP[:\s]+(?P<tp>[\d.]+))?",
        re.IGNORECASE,
    ),
    # Pattern: "🟢 BTC/USDT LONG Entry: 50000-51000"
    re.compile(
        r"(?P<symbol>\w+/\w+)\s+(?P<action>LONG|SHORT)"
        r"(?:.*?[Ee]ntry[:\s]+(?P<price>[\d.]+))"
        r"(?:.*?SL[:\s]+(?P<sl>[\d.]+))?"
        r"(?:.*?TP[:\s]+(?P<tp>[\d.]+))?",
        re.IGNORECASE,
    ),
    # Pattern: "Signal: BUY BTCUSDT Price: 50000"
    re.compile(
        r"[Ss]ignal[:\s]+(?P<action>BUY|SELL)\s+(?P<pair>\w+)"
        r"(?:.*?[Pp]rice[:\s]+(?P<price>[\d.]+))?"
        r"(?:.*?SL[:\s]+(?P<sl>[\d.]+))?"
        r"(?:.*?TP[:\s]+(?P<tp>[\d.]+))?",
        re.IGNORECASE,
    ),
]

# Map Binance-style pairs to ccxt format
PAIR_MAP = {
    "BTCUSDT": "BTC/USDT",
    "ETHUSDT": "ETH/USDT",
    "SOLUSDT": "SOL/USDT",
    "BNBUSDT": "BNB/USDT",
    "XRPUSDT": "XRP/USDT",
    "ADAUSDT": "ADA/USDT",
    "DOGEUSDT": "DOGE/USDT",
    "AVAXUSDT": "AVAX/USDT",
    "DOTUSDT": "DOT/USDT",
    "MATICUSDT": "MATIC/USDT",
}


class SignalFollower(BaseStrategy):
    """
    Parses trading signals from Telegram channels and executes trades.

    Signal Workflow:
    1. Receive signal text from Telegram
    2. Parse signal format (symbol, action, entry, SL, TP)
    3. Validate signal against risk rules
    4. Execute trade through order manager
    5. Record signal in database
    """

    def __init__(
        self,
        order_manager,
        exchange_client,
        risk_manager=None,
        notifier=None,
        default_amount_usdt: float = 100.0,
        min_confidence: float = 0.5,
    ):
        super().__init__("signal", order_manager, risk_manager, notifier)
        self.exchange = exchange_client
        self.default_amount_usdt = default_amount_usdt
        self.min_confidence = min_confidence

        # Queue of pending signals to process
        self._signal_queue: list[dict] = []

    def run(self) -> list:
        """Process any queued signals."""
        if not self.is_active:
            return []

        orders = []
        while self._signal_queue:
            signal_data = self._signal_queue.pop(0)
            try:
                order = self._process_signal(signal_data)
                if order:
                    orders.append(order)
            except Exception as e:
                logger.error("Error processing signal: %s", e)

        return orders

    def receive_signal(self, text: str, source: str = "telegram") -> Optional[dict]:
        """
        Parse a signal from text and queue it for processing.
        Returns parsed signal data or None if parsing failed.
        """
        signal = self.parse_signal(text)
        if signal:
            signal["source"] = source
            signal["raw_text"] = text
            self._signal_queue.append(signal)
            logger.info(
                "Signal queued: %s %s @ %s (SL: %s, TP: %s)",
                signal["action"], signal["symbol"],
                signal.get("price", "market"),
                signal.get("stop_loss", "none"),
                signal.get("take_profit", "none"),
            )
        else:
            logger.debug("Could not parse signal from text: %s", text[:100])
        return signal

    @staticmethod
    def parse_signal(text: str) -> Optional[dict]:
        """
        Parse trading signal from text.
        Returns dict with: symbol, action, price, stop_loss, take_profit
        """
        for pattern in SIGNAL_PATTERNS:
            match = pattern.search(text)
            if match:
                groups = match.groupdict()

                # Normalize symbol
                symbol = groups.get("symbol") or groups.get("pair", "")
                symbol = symbol.upper()
                if "/" not in symbol:
                    symbol = PAIR_MAP.get(symbol, f"{symbol[:len(symbol)-4]}/{symbol[len(symbol)-4:]}")

                # Normalize action
                action = groups.get("action", "").upper()
                if action in ("LONG", "BUY"):
                    action = "buy"
                elif action in ("SHORT", "SELL"):
                    action = "sell"
                else:
                    continue

                return {
                    "symbol": symbol,
                    "action": action,
                    "price": float(groups["price"]) if groups.get("price") else None,
                    "stop_loss": float(groups["sl"]) if groups.get("sl") else None,
                    "take_profit": float(groups["tp"]) if groups.get("tp") else None,
                }

        return None

    def get_status(self) -> dict:
        """Get signal follower strategy status."""
        session = get_session()
        try:
            total_signals = session.query(Signal).filter_by(source="telegram").count()
            acted_on = (
                session.query(Signal)
                .filter_by(source="telegram", acted_on=True)
                .count()
            )
            return {
                "strategy": "signal",
                "is_active": self.is_active,
                "pending_signals": len(self._signal_queue),
                "total_signals_received": total_signals,
                "signals_acted_on": acted_on,
                "default_amount_usdt": self.default_amount_usdt,
            }
        finally:
            session.close()

    def _process_signal(self, signal_data: dict) -> Optional[dict]:
        """Process a parsed signal and execute the trade."""
        session = get_session()
        try:
            symbol = signal_data["symbol"]
            action = signal_data["action"]

            # Record signal in database
            signal = Signal(
                source=signal_data.get("source", "telegram"),
                symbol=symbol,
                action=action,
                confidence=0.8,  # External signals get default confidence
                metadata_json=str(signal_data),
                acted_on=False,
            )
            session.add(signal)
            session.flush()  # Get signal ID

            # Calculate amount
            price = signal_data.get("price")
            if not price:
                price = self.exchange.get_price(symbol)

            amount = self.default_amount_usdt / price

            # Place the order
            order = self._place_order(
                symbol=symbol,
                side=action,
                amount=amount,
                stop_loss=signal_data.get("stop_loss"),
                take_profit=signal_data.get("take_profit"),
                signal_id=signal.id,
            )

            if order:
                signal.acted_on = True
                if self.notifier:
                    self.notifier.send(
                        f"📡 SIGNAL TRADE: {action.upper()} {symbol}\n"
                        f"Amount: {amount:.6f} ({self.default_amount_usdt} USDT)\n"
                        f"Price: {price}\n"
                        f"SL: {signal_data.get('stop_loss', 'auto')}\n"
                        f"TP: {signal_data.get('take_profit', 'auto')}"
                    )

            session.commit()
            return order

        except Exception as e:
            session.rollback()
            logger.error("Failed to process signal: %s", e)
            return None
        finally:
            session.close()
