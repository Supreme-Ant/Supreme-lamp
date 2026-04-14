"""Paper trading simulator - uses real market data but simulates order execution."""

import logging
import time
import uuid
from datetime import datetime
from typing import Optional

import ccxt

logger = logging.getLogger(__name__)


class PaperTrader:
    """
    Simulates exchange trading using real market prices from Binance.
    Maintains virtual balances and tracks all simulated trades.
    Implements the same interface as ExchangeClient.
    """

    def __init__(self, initial_balance_usdt: float = 10000.0):
        # Public-only ccxt instance for fetching real market data
        self.exchange = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

        # Virtual balances: {"USDT": 10000.0, "BTC": 0.5, ...}
        self.balances = {"USDT": initial_balance_usdt}

        # Track all paper orders
        self.orders = []

        # Track open orders (limit orders waiting to fill)
        self.pending_orders = []

        self._markets_loaded = False
        logger.info(
            "Paper trader initialized with %.2f USDT", initial_balance_usdt
        )

    def connect(self) -> bool:
        """Load markets from Binance for real price data."""
        try:
            self.exchange.load_markets()
            self._markets_loaded = True
            logger.info("Paper trader connected. Using real Binance market data.")
            return True
        except ccxt.BaseError as e:
            logger.error("Failed to connect paper trader: %s", e)
            return False

    def get_balance(self) -> dict:
        """Return virtual balances."""
        result = {}
        for currency, total in self.balances.items():
            if total > 0:
                result[currency] = {
                    "free": total,
                    "used": 0.0,
                    "total": total,
                }
        return result

    def get_ticker(self, symbol: str) -> dict:
        """Fetch real ticker from Binance."""
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
        """Fetch real OHLCV data from Binance."""
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
        Simulate order execution.
        Market orders are filled immediately at current price.
        Limit orders are stored as pending.
        """
        # Get current market price
        ticker = self.get_ticker(symbol)
        current_price = ticker["last"]

        # Parse symbol (e.g., "BTC/USDT" -> base="BTC", quote="USDT")
        base, quote = symbol.split("/")

        order_id = f"paper_{uuid.uuid4().hex[:12]}"

        if order_type == "market":
            fill_price = current_price
            return self._execute_fill(
                order_id, symbol, base, quote, side, amount, fill_price
            )
        elif order_type == "limit":
            # Store as pending order
            pending = {
                "id": order_id,
                "symbol": symbol,
                "base": base,
                "quote": quote,
                "side": side,
                "type": "limit",
                "amount": amount,
                "price": price,
                "status": "open",
                "timestamp": int(time.time() * 1000),
                "datetime": datetime.utcnow().isoformat(),
            }
            self.pending_orders.append(pending)
            logger.info(
                "[PAPER] Limit order placed: %s %s %s @ %s",
                side, amount, symbol, price,
            )
            return pending
        else:
            raise ValueError(f"Unsupported order type: {order_type}")

    def _execute_fill(
        self,
        order_id: str,
        symbol: str,
        base: str,
        quote: str,
        side: str,
        amount: float,
        fill_price: float,
    ) -> dict:
        """Execute a simulated fill and update virtual balances."""
        cost = amount * fill_price
        fee = cost * 0.001  # 0.1% trading fee (Binance default)

        if side == "buy":
            # Check if we have enough quote currency
            quote_balance = self.balances.get(quote, 0)
            total_cost = cost + fee
            if quote_balance < total_cost:
                raise ccxt.InsufficientFunds(
                    f"Insufficient {quote}: need {total_cost:.2f}, have {quote_balance:.2f}"
                )
            # Deduct quote, add base
            self.balances[quote] = quote_balance - total_cost
            self.balances[base] = self.balances.get(base, 0) + amount

        elif side == "sell":
            # Check if we have enough base currency
            base_balance = self.balances.get(base, 0)
            if base_balance < amount:
                raise ccxt.InsufficientFunds(
                    f"Insufficient {base}: need {amount}, have {base_balance}"
                )
            # Deduct base, add quote (minus fee)
            self.balances[base] = base_balance - amount
            self.balances[quote] = self.balances.get(quote, 0) + (cost - fee)

        order = {
            "id": order_id,
            "symbol": symbol,
            "type": "market",
            "side": side,
            "amount": amount,
            "filled": amount,
            "price": fill_price,
            "average": fill_price,
            "cost": cost,
            "fee": {"cost": fee, "currency": quote},
            "status": "closed",
            "timestamp": int(time.time() * 1000),
            "datetime": datetime.utcnow().isoformat(),
        }

        self.orders.append(order)
        logger.info(
            "[PAPER] %s %s %s @ %.4f | Cost: %.2f %s | Fee: %.4f",
            side.upper(), amount, symbol, fill_price, cost, quote, fee,
        )

        return order

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """Cancel a pending paper order."""
        for i, order in enumerate(self.pending_orders):
            if order["id"] == order_id:
                order["status"] = "canceled"
                self.orders.append(order)
                self.pending_orders.pop(i)
                logger.info("[PAPER] Order %s cancelled", order_id)
                return order
        raise ccxt.OrderNotFound(f"Order {order_id} not found")

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get pending paper orders."""
        if symbol:
            return [o for o in self.pending_orders if o["symbol"] == symbol]
        return self.pending_orders.copy()

    def get_my_trades(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: int = 100,
    ) -> list:
        """Get filled paper trades."""
        trades = [o for o in self.orders if o["status"] == "closed"]
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]
        if since:
            trades = [t for t in trades if t["timestamp"] >= since]
        return trades[-limit:]

    def check_pending_orders(self) -> list:
        """
        Check if any limit orders should be filled based on current prices.
        Called periodically by the scheduler.
        """
        filled = []
        remaining = []

        for order in self.pending_orders:
            try:
                ticker = self.get_ticker(order["symbol"])
                current_price = ticker["last"]

                should_fill = False
                if order["side"] == "buy" and current_price <= order["price"]:
                    should_fill = True
                elif order["side"] == "sell" and current_price >= order["price"]:
                    should_fill = True

                if should_fill:
                    result = self._execute_fill(
                        order["id"],
                        order["symbol"],
                        order["base"],
                        order["quote"],
                        order["side"],
                        order["amount"],
                        order["price"],
                    )
                    filled.append(result)
                else:
                    remaining.append(order)
            except Exception as e:
                logger.error("Error checking pending order %s: %s", order["id"], e)
                remaining.append(order)

        self.pending_orders = remaining
        return filled

    def withdraw(
        self,
        currency: str,
        amount: float,
        address: str,
        tag: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> dict:
        """Simulate a withdrawal (deducts from virtual balance)."""
        balance = self.balances.get(currency, 0)
        if balance < amount:
            raise ccxt.InsufficientFunds(
                f"Insufficient {currency}: need {amount}, have {balance}"
            )
        self.balances[currency] = balance - amount
        logger.info("[PAPER] Simulated withdrawal: %s %s", amount, currency)
        return {
            "id": f"paper_wd_{uuid.uuid4().hex[:8]}",
            "currency": currency,
            "amount": amount,
            "address": address,
            "status": "ok",
            "timestamp": int(time.time() * 1000),
        }

    def get_price(self, symbol: str) -> float:
        """Get the current last price for a symbol."""
        ticker = self.get_ticker(symbol)
        return ticker["last"]

    def get_total_value_usdt(self) -> float:
        """Calculate total portfolio value in USDT."""
        total = self.balances.get("USDT", 0)
        for currency, amount in self.balances.items():
            if currency == "USDT" or amount <= 0:
                continue
            try:
                price = self.get_price(f"{currency}/USDT")
                total += amount * price
            except Exception:
                logger.warning("Could not get price for %s/USDT", currency)
        return total

    def get_markets(self) -> dict:
        """Get all available trading markets."""
        if not self._markets_loaded:
            self.connect()
        return self.exchange.markets
