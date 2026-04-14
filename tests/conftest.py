"""Shared test fixtures for the trading bot."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bot.database.models import Base


@pytest.fixture
def test_db(monkeypatch):
    """In-memory SQLite database with all tables created."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Patch get_session to return our test session
    import bot.database.db as db_module
    monkeypatch.setattr(db_module, "_engine", engine)
    monkeypatch.setattr(db_module, "_SessionFactory", Session)

    yield session
    session.close()


@pytest.fixture
def sample_ohlcv():
    """Generate realistic OHLCV data for testing (200 candles of BTC/USDT ~50000)."""
    np.random.seed(42)
    n = 200
    base_price = 50000
    timestamps = [
        int((datetime.utcnow() - timedelta(hours=n - i)).timestamp() * 1000)
        for i in range(n)
    ]

    prices = [base_price]
    for _ in range(n - 1):
        change = np.random.normal(0, 0.005)  # 0.5% std dev
        prices.append(prices[-1] * (1 + change))

    ohlcv = []
    for i in range(n):
        close = prices[i]
        high = close * (1 + abs(np.random.normal(0, 0.003)))
        low = close * (1 - abs(np.random.normal(0, 0.003)))
        open_ = close * (1 + np.random.normal(0, 0.002))
        volume = np.random.uniform(100, 1000)
        ohlcv.append([timestamps[i], open_, high, low, close, volume])

    return ohlcv


@pytest.fixture
def sample_dataframe(sample_ohlcv):
    """Convert sample OHLCV to a pandas DataFrame."""
    df = pd.DataFrame(
        sample_ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    return df


class MockExchangeClient:
    """Mock exchange client for testing."""

    def __init__(self, balance_usdt: float = 10000.0, prices: dict = None):
        self.balances = {"USDT": balance_usdt}
        self._prices = prices or {"BTC/USDT": 50000.0, "ETH/USDT": 3000.0}
        self.orders_placed = []

    def connect(self):
        return True

    def get_balance(self):
        result = {}
        for cur, total in self.balances.items():
            result[cur] = {"free": total, "used": 0, "total": total}
        return result

    def get_price(self, symbol):
        return self._prices.get(symbol, 100.0)

    def get_ticker(self, symbol):
        price = self._prices.get(symbol, 100.0)
        return {"symbol": symbol, "last": price, "bid": price * 0.999, "ask": price * 1.001}

    def get_ohlcv(self, symbol, timeframe="1h", since=None, limit=200):
        """Return minimal OHLCV data."""
        np.random.seed(42)
        price = self._prices.get(symbol, 50000)
        data = []
        for i in range(limit):
            ts = int((datetime.utcnow() - timedelta(hours=limit - i)).timestamp() * 1000)
            c = price * (1 + np.random.normal(0, 0.005))
            h = c * 1.003
            l = c * 0.997
            o = c * (1 + np.random.normal(0, 0.002))
            v = np.random.uniform(100, 500)
            data.append([ts, o, h, l, c, v])
        return data

    def create_order(self, symbol, side, order_type="market", amount=0, price=None):
        fill_price = price or self._prices.get(symbol, 100.0)
        order = {
            "id": f"mock_{len(self.orders_placed)}",
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "filled": amount,
            "price": fill_price,
            "average": fill_price,
            "cost": amount * fill_price,
            "fee": {"cost": amount * fill_price * 0.001, "currency": "USDT"},
            "status": "closed",
        }
        self.orders_placed.append(order)

        # Update balances
        base = symbol.split("/")[0]
        if side == "buy":
            cost = amount * fill_price
            self.balances["USDT"] = self.balances.get("USDT", 0) - cost
            self.balances[base] = self.balances.get(base, 0) + amount
        elif side == "sell":
            revenue = amount * fill_price
            self.balances[base] = self.balances.get(base, 0) - amount
            self.balances["USDT"] = self.balances.get("USDT", 0) + revenue

        return order

    def get_my_trades(self, symbol=None, since=None, limit=100):
        return self.orders_placed[-limit:]

    def get_open_orders(self, symbol=None):
        return []

    def cancel_order(self, order_id, symbol):
        return {"id": order_id, "status": "canceled"}

    def withdraw(self, currency, amount, address, tag=None, params=None):
        return {"id": "mock_wd_1", "status": "ok"}


@pytest.fixture
def mock_exchange():
    """Return a mock exchange client with $10,000 USDT."""
    return MockExchangeClient(balance_usdt=10000.0)
