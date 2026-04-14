"""Tests for trading strategies."""

import pytest
from bot.strategies.signal_follower import SignalFollower


class TestSignalParsing:
    """Test Telegram signal parsing."""

    def test_parse_buy_signal(self):
        text = "BUY BTC/USDT @ 50000 SL: 48000 TP: 55000"
        result = SignalFollower.parse_signal(text)
        assert result is not None
        assert result["symbol"] == "BTC/USDT"
        assert result["action"] == "buy"
        assert result["price"] == 50000.0
        assert result["stop_loss"] == 48000.0
        assert result["take_profit"] == 55000.0

    def test_parse_sell_signal(self):
        text = "SELL ETH/USDT @ 3000 SL: 3100 TP: 2800"
        result = SignalFollower.parse_signal(text)
        assert result is not None
        assert result["symbol"] == "ETH/USDT"
        assert result["action"] == "sell"
        assert result["price"] == 3000.0

    def test_parse_long_format(self):
        text = "ETH/USDT LONG Entry: 3000 SL: 2900 TP: 3200"
        result = SignalFollower.parse_signal(text)
        assert result is not None
        assert result["action"] == "buy"
        assert result["price"] == 3000.0

    def test_parse_short_format(self):
        text = "BTC/USDT SHORT Entry: 50000 SL: 52000 TP: 45000"
        result = SignalFollower.parse_signal(text)
        assert result is not None
        assert result["action"] == "sell"
        assert result["price"] == 50000.0

    def test_parse_signal_format(self):
        text = "Signal: BUY BTCUSDT Price: 50000 SL: 48000 TP: 55000"
        result = SignalFollower.parse_signal(text)
        assert result is not None
        assert result["action"] == "buy"
        assert result["price"] == 50000.0

    def test_parse_pair_mapping(self):
        text = "Signal: BUY ETHUSDT Price: 3000"
        result = SignalFollower.parse_signal(text)
        assert result is not None
        assert result["symbol"] == "ETH/USDT"

    def test_parse_no_sl_tp(self):
        text = "BUY SOL/USDT @ 100"
        result = SignalFollower.parse_signal(text)
        assert result is not None
        assert result["stop_loss"] is None
        assert result["take_profit"] is None

    def test_parse_invalid_text(self):
        result = SignalFollower.parse_signal("Hello world")
        assert result is None

    def test_parse_empty_text(self):
        result = SignalFollower.parse_signal("")
        assert result is None


class TestSignalFollower:
    """Test signal follower strategy."""

    def test_receive_and_queue(self, mock_exchange):
        from bot.exchange.order_manager import OrderManager
        om = OrderManager.__new__(OrderManager)
        om.client = mock_exchange
        om.risk_manager = None
        om.notifier = None
        om.is_paper = True

        sf = SignalFollower(
            order_manager=om,
            exchange_client=mock_exchange,
            default_amount_usdt=100.0,
        )

        signal = sf.receive_signal("BUY BTC/USDT @ 50000 SL: 48000 TP: 55000")
        assert signal is not None
        assert signal["action"] == "buy"
        assert len(sf._signal_queue) == 1

    def test_inactive_strategy_skips(self, mock_exchange):
        from bot.exchange.order_manager import OrderManager
        om = OrderManager.__new__(OrderManager)
        om.client = mock_exchange
        om.risk_manager = None
        om.notifier = None
        om.is_paper = True

        sf = SignalFollower(
            order_manager=om,
            exchange_client=mock_exchange,
        )
        sf.stop()

        result = sf.run()
        assert result == []
