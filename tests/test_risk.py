"""Tests for risk management system."""

import pytest
from datetime import datetime, timedelta

from bot.risk.manager import RiskManager
from bot.database.models import Position, Trade, PortfolioSnapshot


class TestRiskManager:
    """Test risk management rules."""

    def test_calculate_sl_tp_buy(self):
        rm = RiskManager(stop_loss_pct=3.0, take_profit_pct=6.0)
        sl, tp = rm._calculate_sl_tp(50000.0, "buy")
        assert sl == pytest.approx(48500.0, rel=1e-6)  # 50000 * 0.97
        assert tp == pytest.approx(53000.0, rel=1e-6)  # 50000 * 1.06

    def test_calculate_sl_tp_sell(self):
        rm = RiskManager(stop_loss_pct=3.0, take_profit_pct=6.0)
        sl, tp = rm._calculate_sl_tp(50000.0, "sell")
        assert sl == pytest.approx(51500.0, rel=1e-6)  # 50000 * 1.03
        assert tp == pytest.approx(47000.0, rel=1e-6)  # 50000 * 0.94

    def test_cooldown_not_active_initially(self):
        rm = RiskManager(cooldown_after_losses=3)
        assert rm._is_in_cooldown() is False

    def test_cooldown_activates_after_consecutive_losses(self):
        rm = RiskManager(cooldown_after_losses=3, cooldown_minutes=60)
        rm.post_trade_update(trade_pnl=-100)
        rm.post_trade_update(trade_pnl=-50)
        rm.post_trade_update(trade_pnl=-75)
        assert rm._is_in_cooldown() is True

    def test_cooldown_resets_on_win(self):
        rm = RiskManager(cooldown_after_losses=3)
        rm.post_trade_update(trade_pnl=-100)
        rm.post_trade_update(trade_pnl=-50)
        rm.post_trade_update(trade_pnl=200)  # Win resets counter
        assert rm._consecutive_losses == 0
        assert rm._is_in_cooldown() is False

    def test_reject_format(self):
        result = RiskManager._reject("test reason")
        assert result["allowed"] is False
        assert result["reason"] == "test reason"
        assert result["adjusted_amount"] == 0
        assert result["stop_loss"] == 0
        assert result["take_profit"] == 0

    def test_pre_trade_check_max_positions(self, test_db):
        rm = RiskManager(max_positions=2)
        rm._peak_balance = 10000

        # Create 2 open positions
        for i in range(2):
            pos = Position(
                symbol=f"TOKEN{i}/USDT",
                side="long",
                entry_price=100,
                amount=1,
                strategy="test",
                is_open=True,
            )
            test_db.add(pos)
        test_db.commit()

        result = rm.pre_trade_check("NEW/USDT", "buy", 1.0, 100.0)
        assert result["allowed"] is False
        assert "Max positions" in result["reason"]

    def test_pre_trade_check_passes(self, test_db):
        rm = RiskManager(max_positions=5, max_position_size_pct=10.0)
        rm._peak_balance = 10000

        # Add a portfolio snapshot so position sizing works
        snapshot = PortfolioSnapshot(
            total_balance=10000, available_balance=10000,
            in_positions=0, total_pnl=0, daily_pnl=0
        )
        test_db.add(snapshot)
        test_db.commit()

        result = rm.pre_trade_check("BTC/USDT", "buy", 0.01, 50000.0)
        assert result["allowed"] is True
        assert result["stop_loss"] > 0
        assert result["take_profit"] > 0

    def test_position_size_adjustment(self, test_db):
        rm = RiskManager(max_position_size_pct=10.0)

        # Portfolio is $10,000 -> max position = $1,000
        snapshot = PortfolioSnapshot(
            total_balance=10000, available_balance=10000, in_positions=0
        )
        test_db.add(snapshot)
        test_db.commit()

        # Requesting $2,000 position should be reduced to $1,000
        adjusted = rm._check_position_size(test_db, "BTC/USDT", 0.04, 50000.0)
        # 0.04 * 50000 = 2000 > 1000, should be reduced to 1000/50000 = 0.02
        assert adjusted == pytest.approx(0.02, rel=1e-6)

    def test_update_peak_balance(self):
        rm = RiskManager()
        rm.update_peak_balance(10000)
        assert rm._peak_balance == 10000
        rm.update_peak_balance(12000)
        assert rm._peak_balance == 12000
        rm.update_peak_balance(11000)  # Should not decrease
        assert rm._peak_balance == 12000

    def test_daily_pnl_calculation(self, test_db):
        rm = RiskManager()

        # Add some trades with PnL
        for pnl in [100, -50, 200]:
            trade = Trade(
                symbol="BTC/USDT", side="sell", amount=0.01,
                strategy="test", status="filled", pnl=pnl,
                created_at=datetime.utcnow(),
            )
            test_db.add(trade)
        test_db.commit()

        daily_pnl = rm._get_daily_pnl(test_db)
        assert daily_pnl == 250  # 100 - 50 + 200

    def test_max_drawdown_not_exceeded(self, test_db):
        rm = RiskManager(max_drawdown_pct=15.0)
        rm._peak_balance = 10000

        # Portfolio dropped 10% -> still under 15% limit
        snapshot = PortfolioSnapshot(
            total_balance=9000, available_balance=9000, in_positions=0
        )
        test_db.add(snapshot)
        test_db.commit()

        assert rm._is_max_drawdown_exceeded(test_db) is False

    def test_max_drawdown_exceeded(self, test_db):
        rm = RiskManager(max_drawdown_pct=15.0)
        rm._peak_balance = 10000

        # Portfolio dropped 20% -> exceeds 15% limit
        snapshot = PortfolioSnapshot(
            total_balance=8000, available_balance=8000, in_positions=0
        )
        test_db.add(snapshot)
        test_db.commit()

        assert rm._is_max_drawdown_exceeded(test_db) is True
