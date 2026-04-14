"""AI autonomous trading strategy - uses ML model and technical analysis."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from bot.strategies.base import BaseStrategy
from bot.ai.signals import SignalGenerator
from bot.database.db import get_session
from bot.database.models import Signal, Trade

logger = logging.getLogger(__name__)


class AITrader(BaseStrategy):
    """
    Autonomous AI-powered trading strategy.

    Workflow:
    1. Generate signals for configured symbols using TA + ML
    2. Filter signals by confidence threshold
    3. Execute trades through order manager with risk checks
    4. Periodically retrain ML models on recent data
    """

    def __init__(
        self,
        order_manager,
        exchange_client,
        risk_manager=None,
        notifier=None,
        symbols: Optional[list[str]] = None,
        timeframes: Optional[list[str]] = None,
        confidence_threshold: float = 0.7,
        default_amount_usdt: float = 100.0,
        retrain_hours: int = 24,
        lookback_days: int = 30,
    ):
        super().__init__("ai", order_manager, risk_manager, notifier)
        self.exchange = exchange_client
        self.symbols = symbols or ["BTC/USDT", "ETH/USDT"]
        self.timeframes = timeframes or ["1h"]
        self.confidence_threshold = confidence_threshold
        self.default_amount_usdt = default_amount_usdt
        self.retrain_hours = retrain_hours
        self.lookback_days = lookback_days

        # Signal generator
        self.signal_generator = SignalGenerator(
            exchange_client=exchange_client,
            min_confidence=confidence_threshold,
        )

        # Track last training time
        self._last_train_time: Optional[datetime] = None

    def run(self) -> list:
        """
        Execute one AI trading cycle.
        Generates signals for all configured symbols and acts on strong signals.
        """
        if not self.is_active:
            return []

        # Check if models need retraining
        self._maybe_retrain()

        orders = []
        for timeframe in self.timeframes:
            for symbol in self.symbols:
                try:
                    order = self._analyze_and_trade(symbol, timeframe)
                    if order:
                        orders.append(order)
                except Exception as e:
                    logger.error("AI trading error for %s %s: %s", symbol, timeframe, e)

        return orders

    def train_models(self) -> dict:
        """Train ML models for all configured symbols."""
        results = {}
        for symbol in self.symbols:
            for timeframe in self.timeframes:
                try:
                    metrics = self.signal_generator.train_model(
                        symbol=symbol,
                        timeframe=timeframe,
                        lookback_days=self.lookback_days,
                    )
                    results[f"{symbol}_{timeframe}"] = metrics
                    logger.info("Trained model for %s %s: %s", symbol, timeframe, metrics)
                except Exception as e:
                    logger.error("Failed to train model for %s %s: %s", symbol, timeframe, e)
                    results[f"{symbol}_{timeframe}"] = {"error": str(e)}

        self._last_train_time = datetime.utcnow()
        return results

    def get_status(self) -> dict:
        """Get AI trading strategy status."""
        session = get_session()
        try:
            total_signals = session.query(Signal).filter_by(source="ai").count()
            acted_on = session.query(Signal).filter_by(source="ai", acted_on=True).count()
            total_trades = session.query(Trade).filter_by(strategy="ai").count()
            total_pnl = sum(
                t.pnl or 0
                for t in session.query(Trade)
                .filter_by(strategy="ai")
                .filter(Trade.pnl.isnot(None))
                .all()
            )

            # Model status
            model_status = {}
            for symbol in self.symbols:
                model = self.signal_generator.get_or_create_model(symbol)
                model_status[symbol] = {
                    "trained": model.is_trained,
                    "top_features": dict(list(model.get_feature_importance().items())[:5]),
                }

            return {
                "strategy": "ai",
                "is_active": self.is_active,
                "symbols": self.symbols,
                "timeframes": self.timeframes,
                "confidence_threshold": self.confidence_threshold,
                "total_signals": total_signals,
                "signals_acted_on": acted_on,
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "last_training": self._last_train_time.isoformat() if self._last_train_time else None,
                "models": model_status,
            }
        finally:
            session.close()

    def get_latest_signals(self) -> list:
        """Get the most recent AI signals."""
        session = get_session()
        try:
            signals = (
                session.query(Signal)
                .filter_by(source="ai")
                .order_by(Signal.created_at.desc())
                .limit(20)
                .all()
            )
            return [
                {
                    "id": s.id,
                    "symbol": s.symbol,
                    "timeframe": s.timeframe,
                    "action": s.action,
                    "confidence": s.confidence,
                    "ta_score": s.ta_score,
                    "ml_score": s.ml_score,
                    "acted_on": s.acted_on,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in signals
            ]
        finally:
            session.close()

    def _analyze_and_trade(self, symbol: str, timeframe: str) -> Optional[dict]:
        """Analyze a symbol and trade if signal is strong enough."""
        signal = self.signal_generator.generate_signal(symbol, timeframe)
        if not signal:
            return None

        # Only act on strong buy/sell signals
        if signal["action"] == "hold":
            return None

        if signal["confidence"] < self.confidence_threshold:
            logger.debug(
                "Signal for %s too weak: %.2f < %.2f",
                symbol, signal["confidence"], self.confidence_threshold,
            )
            return None

        # Calculate position size
        price = self.exchange.get_price(symbol)
        amount = self.default_amount_usdt / price

        # Scale amount by confidence (higher confidence = larger position)
        confidence_scale = 0.5 + (signal["confidence"] * 0.5)  # 0.5x to 1.0x
        amount *= confidence_scale

        # Place the order
        order = self._place_order(
            symbol=symbol,
            side=signal["action"],
            amount=amount,
            signal_id=signal["signal_id"],
        )

        if order:
            # Mark signal as acted on
            self._mark_signal_acted(signal["signal_id"])

            if self.notifier:
                self.notifier.send(
                    f"🤖 AI TRADE: {signal['action'].upper()} {symbol}\n"
                    f"Confidence: {signal['confidence']:.1%}\n"
                    f"TA Score: {signal['ta_score']:.2f} | ML Score: {signal['ml_score']:.2f}\n"
                    f"Amount: {amount:.6f} ({self.default_amount_usdt * confidence_scale:.0f} USDT)\n"
                    f"Timeframe: {timeframe}"
                )

        return order

    def _maybe_retrain(self):
        """Retrain models if enough time has passed."""
        if self._last_train_time is None:
            # First run - train models
            logger.info("Initial model training...")
            self.train_models()
            return

        elapsed = datetime.utcnow() - self._last_train_time
        if elapsed > timedelta(hours=self.retrain_hours):
            logger.info("Retraining models (last trained %s ago)", elapsed)
            self.train_models()

    @staticmethod
    def _mark_signal_acted(signal_id: int):
        """Mark a signal as acted on in the database."""
        session = get_session()
        try:
            signal = session.query(Signal).filter_by(id=signal_id).first()
            if signal:
                signal.acted_on = True
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Failed to mark signal as acted: %s", e)
        finally:
            session.close()
