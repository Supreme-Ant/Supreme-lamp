"""AI signal generation - combines technical analysis and ML predictions."""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from bot.ai.feature_engine import FeatureEngine
from bot.ai.model import TradingModel
from bot.database.db import get_session
from bot.database.models import Signal

logger = logging.getLogger(__name__)


class SignalGenerator:
    """
    Orchestrates the AI signal pipeline:
    1. Fetch OHLCV data from exchange
    2. Compute technical indicators
    3. Build feature vector
    4. Get ML prediction
    5. Combine TA score and ML score into final signal
    6. Persist signal to DB
    """

    def __init__(
        self,
        exchange_client,
        ta_weight: float = 0.4,
        ml_weight: float = 0.6,
        min_confidence: float = 0.65,
    ):
        self.exchange = exchange_client
        self.feature_engine = FeatureEngine()
        self.models: dict[str, TradingModel] = {}
        self.ta_weight = ta_weight
        self.ml_weight = ml_weight
        self.min_confidence = min_confidence

    def get_or_create_model(self, symbol: str) -> TradingModel:
        """Get or create a model for a specific symbol."""
        model_name = symbol.replace("/", "_").lower()
        if model_name not in self.models:
            model = TradingModel(model_name)
            if not model.load():
                logger.info("No saved model for %s, will need training", symbol)
            self.models[model_name] = model
        return self.models[model_name]

    def train_model(
        self,
        symbol: str,
        timeframe: str = "1h",
        lookback_days: int = 30,
        lookahead_candles: int = 5,
        threshold: float = 0.01,
    ) -> dict:
        """
        Train (or retrain) the ML model for a symbol.

        Fetches historical OHLCV data, computes features, and trains the model.
        """
        logger.info("Training model for %s (%s, %d days)", symbol, timeframe, lookback_days)

        # Calculate how many candles we need
        candles_per_day = {"1h": 24, "4h": 6, "1d": 1, "15m": 96}
        limit = lookback_days * candles_per_day.get(timeframe, 24)
        limit = min(limit, 1000)  # Most exchanges cap at 1000

        # Fetch OHLCV data
        ohlcv = self.exchange.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if len(ohlcv) < 100:
            return {"error": f"Not enough data: {len(ohlcv)} candles (need >= 100)"}

        # Convert to DataFrame
        df = self.feature_engine.ohlcv_to_dataframe(ohlcv)

        # Compute indicators
        df = self.feature_engine.compute_indicators(df)

        # Build features and labels
        features = self.feature_engine.build_features(df)
        labels = self.feature_engine.create_labels(df, lookahead=lookahead_candles, threshold=threshold)

        # Train model
        model = self.get_or_create_model(symbol)
        metrics = model.train(features, labels)

        return metrics

    def generate_signal(self, symbol: str, timeframe: str = "1h") -> Optional[dict]:
        """
        Generate a trading signal for a symbol.

        Returns:
            {
                "symbol": str,
                "timeframe": str,
                "action": "buy" | "sell" | "hold",
                "confidence": float (0-1),
                "ta_score": float (0-1),
                "ml_score": float (0-1),
                "signal_id": int,
            }
        """
        try:
            # Fetch recent OHLCV data
            ohlcv = self.exchange.get_ohlcv(symbol, timeframe=timeframe, limit=200)
            if len(ohlcv) < 60:
                logger.warning("Not enough data for %s: %d candles", symbol, len(ohlcv))
                return None

            # Convert and compute indicators
            df = self.feature_engine.ohlcv_to_dataframe(ohlcv)
            df = self.feature_engine.compute_indicators(df)

            # Get TA score (rule-based)
            ta_score = self.feature_engine.generate_ta_score(df)

            # Get ML score
            ml_score = 0.5  # Default neutral
            model = self.get_or_create_model(symbol)
            if model.is_trained:
                features = self.feature_engine.build_features(df)
                if len(features) > 0:
                    prediction = model.predict(features)
                    ml_score = prediction["probabilities"]["up"]
            else:
                logger.info("Model not trained for %s, using TA only", symbol)

            # Combine scores
            if model.is_trained:
                combined = (self.ta_weight * ta_score) + (self.ml_weight * ml_score)
            else:
                combined = ta_score  # TA only when no model

            # Determine action
            if combined >= 0.5 + (1 - self.min_confidence) / 2:
                action = "buy"
            elif combined <= 0.5 - (1 - self.min_confidence) / 2:
                action = "sell"
            else:
                action = "hold"

            confidence = abs(combined - 0.5) * 2  # Normalize distance from 0.5 to 0-1

            # Record signal in database
            signal_id = self._record_signal(
                symbol=symbol,
                timeframe=timeframe,
                action=action,
                confidence=confidence,
                ta_score=ta_score,
                ml_score=ml_score,
            )

            result = {
                "symbol": symbol,
                "timeframe": timeframe,
                "action": action,
                "confidence": confidence,
                "ta_score": ta_score,
                "ml_score": ml_score,
                "combined_score": combined,
                "signal_id": signal_id,
            }

            logger.info(
                "Signal for %s: %s (confidence=%.2f, ta=%.2f, ml=%.2f)",
                symbol, action, confidence, ta_score, ml_score,
            )

            return result

        except Exception as e:
            logger.error("Failed to generate signal for %s: %s", symbol, e)
            return None

    def generate_signals_batch(
        self, symbols: list[str], timeframe: str = "1h"
    ) -> list[dict]:
        """Generate signals for multiple symbols."""
        signals = []
        for symbol in symbols:
            signal = self.generate_signal(symbol, timeframe)
            if signal:
                signals.append(signal)
        return signals

    def _record_signal(
        self,
        symbol: str,
        timeframe: str,
        action: str,
        confidence: float,
        ta_score: float,
        ml_score: float,
    ) -> int:
        """Record signal in database and return its ID."""
        session = get_session()
        try:
            signal = Signal(
                source="ai",
                symbol=symbol,
                timeframe=timeframe,
                action=action,
                confidence=confidence,
                ta_score=ta_score,
                ml_score=ml_score,
                acted_on=False,
            )
            session.add(signal)
            session.commit()
            return signal.id
        except Exception as e:
            session.rollback()
            logger.error("Failed to record signal: %s", e)
            return -1
        finally:
            session.close()
