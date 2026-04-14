"""Binance exchange client wrapper using ccxt."""

import logging
import time
from typing import Optional

import ccxt

logger = logging.getLogger(__name__)


class ExchangeClient:
    """Wrapper around ccxt.binance for live trading."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
    ):
        self.exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

        if testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("Binance client initialized in TESTNET mode")
        else:
            logger.info("Binance client initialized in LIVE mode")

        self._markets_loaded = False

    def connect(self) -> bool:
        """Load markets and verify connection."""
        try:
            self.exchange.load_markets()
            self._markets_loaded = True
            logger.info("Connected to Binance. %d markets available.", len(self.exchange.markets))
            return True
        except ccxt.BaseError as e:
            logger.error("Failed to connect to Binance: %s", e)
            return False

    def get_balance(self) -> dict:
        """
        Fetch account balance.
        Returns dict like: {"USDT": {"free": 1000.0, "used": 500.0, "total": 1500.0}, ...}
        """
        try:
            balance = self.exchange.fetch_balance()
            # Filter to only non-zero balances
            result = {}
            for currency, amounts in balance.get("total", {}).items():
                if amounts and amounts > 0:
                    result[currency] = {
                        "free": balance["free"].get(currency, 0),
                        "used": balance["used"].get(currency, 0),
                        "total": amounts,
                    }
            return result
        except ccxt.BaseError as e:
            logger.error("Failed to fetch balance: %s", e)
            raise

    def get_ticker(self, symbol: str) -> dict:
        """
        Fetch current ticker for a symbol.
        Returns: {"symbol": "BTC/USDT", "last": 50000.0, "bid": ..., "ask": ..., ...}
        """
        try:
            return self.exchange.fetch_ticker(symbol)
        except ccxt.BaseError as e:
            logger.error("Failed to fetch ticker for %s: %s", symbol, e)
            raise

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: int = 200,
    ) -> list:
        """
        Fetch OHLCV candlestick data.
        Returns list of [timestamp, open, high, low, close, volume].
        """
        try:
            return self.exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, since=since, limit=limit
            )
        except ccxt.BaseError as e:
            logger.error("Failed to fetch OHLCV for %s: %s", symbol, e)
            raise

    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "market",
        amount: float = 0,
        price: Optional[float] = None,
    ) -> dict:
        """
        Place an order on the exchange.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            side: "buy" or "sell"
            order_type: "market" or "limit"
            amount: Quantity to trade
            price: Limit price (required for limit orders)

        Returns:
            Order result dict from ccxt
        """
        try:
            logger.info(
                "Placing %s %s order: %s %s @ %s",
                order_type, side, amount, symbol, price or "market"
            )
            order = self.exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price,
            )
            logger.info("Order placed: %s", order.get("id"))
            return order
        except ccxt.InsufficientFunds as e:
            logger.error("Insufficient funds for %s %s %s: %s", side, amount, symbol, e)
            raise
        except ccxt.InvalidOrder as e:
            logger.error("Invalid order %s %s %s: %s", side, amount, symbol, e)
            raise
        except ccxt.BaseError as e:
            logger.error("Order failed: %s", e)
            raise

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """Cancel an open order."""
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            logger.info("Order %s cancelled", order_id)
            return result
        except ccxt.BaseError as e:
            logger.error("Failed to cancel order %s: %s", order_id, e)
            raise

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Fetch all open orders, optionally filtered by symbol."""
        try:
            return self.exchange.fetch_open_orders(symbol)
        except ccxt.BaseError as e:
            logger.error("Failed to fetch open orders: %s", e)
            raise

    def get_my_trades(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: int = 100,
    ) -> list:
        """Fetch recent trades for the account."""
        try:
            return self.exchange.fetch_my_trades(symbol, since=since, limit=limit)
        except ccxt.BaseError as e:
            logger.error("Failed to fetch trades: %s", e)
            raise

    def withdraw(
        self,
        currency: str,
        amount: float,
        address: str,
        tag: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """
        Withdraw funds from the exchange.

        For crypto: provide the wallet address.
        For fiat: use params dict with exchange-specific bank details.

        Example fiat withdrawal (Binance):
            withdraw("USD", 1000, "", params={"network": "SWIFT", ...})

        Note: Bank accounts must be pre-linked via the exchange's web interface.
        """
        try:
            logger.info("Withdrawing %s %s to %s", amount, currency, address or "bank")
            result = self.exchange.withdraw(
                currency, amount, address, tag=tag, params=params or {}
            )
            logger.info("Withdrawal initiated: %s", result.get("id"))
            return result
        except ccxt.BaseError as e:
            logger.error("Withdrawal failed: %s", e)
            raise

    def get_withdrawal_status(self, withdrawal_id: str) -> dict:
        """Check the status of a withdrawal."""
        try:
            withdrawals = self.exchange.fetch_withdrawals()
            for w in withdrawals:
                if w.get("id") == withdrawal_id:
                    return w
            return {"status": "unknown"}
        except ccxt.BaseError as e:
            logger.error("Failed to check withdrawal status: %s", e)
            raise

    def get_markets(self) -> dict:
        """Get all available trading markets."""
        if not self._markets_loaded:
            self.connect()
        return self.exchange.markets

    def get_price(self, symbol: str) -> float:
        """Get the current last price for a symbol."""
        ticker = self.get_ticker(symbol)
        return ticker["last"]
