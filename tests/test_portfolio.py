"""Tests for portfolio tracking."""

import pytest
from datetime import datetime

from tests.conftest import MockExchangeClient
from bot.portfolio.tracker import PortfolioTracker
from bot.database.models import Position, Trade, PortfolioSnapshot


class TestPortfolioTracker:
    """Test portfolio tracking and PnL calculation."""

    def test_get_summary(self, test_db, mock_exchange):
        tracker = PortfolioTracker(mock_exchange, is_paper=True)
        summary = tracker.get_summary()

        assert "total_value_usdt" in summary
        assert "available_usdt" in summary
        assert "daily_pnl" in summary
        assert "total_pnl" in summary
        assert summary["is_paper"] is True
        assert summary["total_value_usdt"] >= 0

    def test_get_open_positions_empty(self, test_db, mock_exchange):
        tracker = PortfolioTracker(mock_exchange)
        positions = tracker.get_open_positions()
        assert positions == []

    def test_get_open_positions_with_data(self, test_db, mock_exchange):
        # Create a position
        position = Position(
            symbol="BTC/USDT", side="long", entry_price=50000,
            amount=0.1, current_price=51000, unrealized_pnl=100,
            strategy="ai", is_paper=True, is_open=True,
        )
        test_db.add(position)
        test_db.commit()

        tracker = PortfolioTracker(mock_exchange)
        positions = tracker.get_open_positions()

        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTC/USDT"
        assert positions[0]["side"] == "long"
        assert positions[0]["entry_price"] == 50000

    def test_take_snapshot(self, test_db, mock_exchange):
        tracker = PortfolioTracker(mock_exchange)
        tracker.take_snapshot()

        # Verify saved to DB via fresh query
        count = test_db.query(PortfolioSnapshot).count()
        assert count == 1
        snapshot = test_db.query(PortfolioSnapshot).first()
        assert snapshot.total_balance >= 0

    def test_get_trade_history(self, test_db, mock_exchange):
        # Add some trades
        for i in range(3):
            trade = Trade(
                symbol="BTC/USDT", side="buy", amount=0.01,
                strategy="test", status="filled", is_paper=True,
                average_price=50000, cost=500,
            )
            test_db.add(trade)
        test_db.commit()

        tracker = PortfolioTracker(mock_exchange)
        history = tracker.get_trade_history(limit=10)

        assert len(history) == 3
        assert history[0]["symbol"] == "BTC/USDT"

    def test_get_strategy_performance(self, test_db, mock_exchange):
        # Add trades with PnL for different strategies
        trades = [
            Trade(symbol="BTC/USDT", side="sell", amount=0.01, strategy="ai",
                  status="filled", pnl=100),
            Trade(symbol="BTC/USDT", side="sell", amount=0.01, strategy="ai",
                  status="filled", pnl=-50),
            Trade(symbol="ETH/USDT", side="sell", amount=0.1, strategy="copy",
                  status="filled", pnl=200),
        ]
        for t in trades:
            test_db.add(t)
        test_db.commit()

        tracker = PortfolioTracker(mock_exchange)
        performance = tracker.get_strategy_performance()

        assert "ai" in performance
        assert performance["ai"]["total_trades"] == 2
        assert performance["ai"]["total_pnl"] == 50  # 100 - 50
        assert performance["ai"]["winners"] == 1
        assert performance["ai"]["win_rate"] == 50.0

        assert "copy" in performance
        assert performance["copy"]["total_pnl"] == 200

    def test_get_daily_pnl(self, test_db, mock_exchange):
        # Add today's trades
        trade = Trade(
            symbol="BTC/USDT", side="sell", amount=0.01,
            strategy="test", status="filled", pnl=150,
            created_at=datetime.utcnow(),
        )
        test_db.add(trade)
        test_db.commit()

        tracker = PortfolioTracker(mock_exchange)
        summary = tracker.get_summary()
        assert summary["daily_pnl"] == 150

    def test_get_pnl_history(self, test_db, mock_exchange):
        # Add some snapshots
        for i in range(5):
            snapshot = PortfolioSnapshot(
                total_balance=10000 + i * 100,
                available_balance=10000 + i * 100,
                in_positions=0,
                daily_pnl=i * 10,
                total_pnl=i * 50,
            )
            test_db.add(snapshot)
        test_db.commit()

        tracker = PortfolioTracker(mock_exchange)
        history = tracker.get_pnl_history(days=30)
        assert len(history) == 5
