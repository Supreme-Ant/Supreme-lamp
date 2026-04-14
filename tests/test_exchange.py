"""Tests for exchange client and paper trader."""

import pytest
from bot.exchange.paper_trader import PaperTrader


class TestPaperTrader:
    """Test paper trading simulator."""

    def test_initial_balance(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.balances = {"USDT": 10000.0}
        pt.orders = []
        pt.pending_orders = []

        balance = pt.get_balance()
        assert "USDT" in balance
        assert balance["USDT"]["total"] == 10000.0
        assert balance["USDT"]["free"] == 10000.0

    def test_balance_empty_currencies_excluded(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.balances = {"USDT": 10000.0, "BTC": 0.0}
        pt.orders = []
        pt.pending_orders = []

        balance = pt.get_balance()
        assert "USDT" in balance
        assert "BTC" not in balance

    def test_get_open_orders_empty(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.pending_orders = []

        assert pt.get_open_orders() == []

    def test_get_open_orders_filtered(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.pending_orders = [
            {"symbol": "BTC/USDT", "id": "1"},
            {"symbol": "ETH/USDT", "id": "2"},
        ]

        result = pt.get_open_orders("BTC/USDT")
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_get_my_trades_filtered(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.orders = [
            {"symbol": "BTC/USDT", "status": "closed", "timestamp": 1000},
            {"symbol": "ETH/USDT", "status": "closed", "timestamp": 2000},
            {"symbol": "BTC/USDT", "status": "canceled", "timestamp": 3000},
        ]

        trades = pt.get_my_trades(symbol="BTC/USDT")
        assert len(trades) == 1
        assert trades[0]["symbol"] == "BTC/USDT"

    def test_execute_fill_buy(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.balances = {"USDT": 10000.0}
        pt.orders = []
        pt.pending_orders = []

        order = pt._execute_fill(
            "test_1", "BTC/USDT", "BTC", "USDT", "buy", 0.1, 50000.0
        )

        assert order["status"] == "closed"
        assert order["side"] == "buy"
        assert order["amount"] == 0.1
        assert pt.balances["BTC"] == 0.1
        # Cost = 0.1 * 50000 = 5000, fee = 5000 * 0.001 = 5
        assert pt.balances["USDT"] == pytest.approx(10000 - 5000 - 5, rel=1e-6)

    def test_execute_fill_sell(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.balances = {"USDT": 5000.0, "BTC": 0.1}
        pt.orders = []

        order = pt._execute_fill(
            "test_2", "BTC/USDT", "BTC", "USDT", "sell", 0.1, 50000.0
        )

        assert order["status"] == "closed"
        assert pt.balances["BTC"] == 0.0
        # Revenue = 0.1 * 50000 = 5000, fee = 5000 * 0.001 = 5
        assert pt.balances["USDT"] == pytest.approx(5000 + 5000 - 5, rel=1e-6)

    def test_execute_fill_insufficient_funds(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.balances = {"USDT": 100.0}
        pt.orders = []

        import ccxt
        with pytest.raises(ccxt.InsufficientFunds):
            pt._execute_fill(
                "test_3", "BTC/USDT", "BTC", "USDT", "buy", 0.1, 50000.0
            )

    def test_withdraw_deducts_balance(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.balances = {"USDT": 10000.0}

        result = pt.withdraw("USDT", 5000, "bank_account")
        assert result["status"] == "ok"
        assert pt.balances["USDT"] == 5000.0

    def test_withdraw_insufficient(self):
        pt = PaperTrader.__new__(PaperTrader)
        pt.balances = {"USDT": 100.0}

        import ccxt
        with pytest.raises(ccxt.InsufficientFunds):
            pt.withdraw("USDT", 5000, "bank_account")
