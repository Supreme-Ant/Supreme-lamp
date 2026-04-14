"""Tests for AI trading components."""

import pytest
import pandas as pd
import numpy as np

from bot.ai.feature_engine import FeatureEngine
from bot.ai.model import TradingModel


class TestFeatureEngine:
    """Test technical indicator feature extraction."""

    def test_ohlcv_to_dataframe(self, sample_ohlcv):
        df = FeatureEngine.ohlcv_to_dataframe(sample_ohlcv)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 200
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "timestamp"

    def test_compute_indicators(self, sample_dataframe):
        df = FeatureEngine.compute_indicators(sample_dataframe)

        # Verify key indicators exist
        expected_cols = [
            "ema_9", "ema_21", "ema_50", "sma_20", "sma_50",
            "macd", "macd_signal", "macd_hist",
            "rsi_14", "rsi_7",
            "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
            "adx", "adx_pos", "adx_neg",
            "atr",
            "stoch_k", "stoch_d",
            "obv",
            "mfi",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing indicator: {col}"

    def test_build_features(self, sample_dataframe):
        df = FeatureEngine.compute_indicators(sample_dataframe)
        features = FeatureEngine.build_features(df)

        assert isinstance(features, pd.DataFrame)
        assert len(features) > 0
        # Should have no NaN values after dropna
        assert features.isna().sum().sum() == 0

        # Check key feature columns
        expected = [
            "price_change_1", "price_change_5",
            "rsi_14", "macd_hist", "bb_pct",
            "adx", "atr_pct", "volume_ratio",
        ]
        for col in expected:
            assert col in features.columns, f"Missing feature: {col}"

    def test_create_labels(self, sample_dataframe):
        labels = FeatureEngine.create_labels(
            sample_dataframe, lookahead=5, threshold=0.01
        )
        assert isinstance(labels, pd.Series)
        assert set(labels.dropna().unique()).issubset({0, 1})

    def test_generate_ta_score(self, sample_dataframe):
        df = FeatureEngine.compute_indicators(sample_dataframe)
        score = FeatureEngine.generate_ta_score(df)
        assert 0.0 <= score <= 1.0

    def test_generate_ta_score_empty(self):
        df = pd.DataFrame()
        score = FeatureEngine.generate_ta_score(df)
        assert score == 0.5  # Neutral for empty data


class TestTradingModel:
    """Test ML model training and prediction."""

    def test_train_and_predict(self, sample_dataframe):
        df = FeatureEngine.compute_indicators(sample_dataframe)
        features = FeatureEngine.build_features(df)
        labels = FeatureEngine.create_labels(sample_dataframe, lookahead=5, threshold=0.005)

        model = TradingModel(model_name="test_model")
        metrics = model.train(features, labels)

        assert "accuracy" in metrics
        assert "f1" in metrics
        assert "cv_accuracy_mean" in metrics
        assert metrics["accuracy"] > 0
        assert model.is_trained

        # Test prediction
        result = model.predict(features)
        assert result["direction"] in ("buy", "sell", "hold")
        assert 0 <= result["confidence"] <= 1
        assert "up" in result["probabilities"]
        assert "down" in result["probabilities"]

    def test_predict_proba_up(self, sample_dataframe):
        df = FeatureEngine.compute_indicators(sample_dataframe)
        features = FeatureEngine.build_features(df)
        labels = FeatureEngine.create_labels(sample_dataframe, lookahead=5, threshold=0.005)

        model = TradingModel(model_name="test_model_proba")
        model.train(features, labels)

        proba = model.predict_proba_up(features)
        assert 0 <= proba <= 1

    def test_feature_importance(self, sample_dataframe):
        df = FeatureEngine.compute_indicators(sample_dataframe)
        features = FeatureEngine.build_features(df)
        labels = FeatureEngine.create_labels(sample_dataframe, lookahead=5, threshold=0.005)

        model = TradingModel(model_name="test_model_fi")
        model.train(features, labels)

        importance = model.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) > 0

    def test_save_and_load(self, sample_dataframe, tmp_path):
        df = FeatureEngine.compute_indicators(sample_dataframe)
        features = FeatureEngine.build_features(df)
        labels = FeatureEngine.create_labels(sample_dataframe, lookahead=5, threshold=0.005)

        # Train and save
        model = TradingModel(model_name="test_save")
        model.model_path = str(tmp_path / "test_model.joblib")
        model.train(features, labels)

        # Load into new instance
        model2 = TradingModel(model_name="test_save")
        model2.model_path = str(tmp_path / "test_model.joblib")
        assert model2.load() is True
        assert model2.is_trained

        # Predictions should match
        result1 = model.predict(features)
        result2 = model2.predict(features)
        assert result1["direction"] == result2["direction"]

    def test_not_trained_raises(self):
        model = TradingModel(model_name="untrained")
        with pytest.raises(RuntimeError, match="not trained"):
            model.predict(pd.DataFrame({"a": [1, 2, 3]}))

    def test_insufficient_data(self):
        model = TradingModel(model_name="small_data")
        X = pd.DataFrame({"a": range(10), "b": range(10)})
        y = pd.Series([0, 1] * 5)
        with pytest.raises(ValueError, match="Not enough"):
            model.train(X, y)

    def test_load_missing_file(self):
        model = TradingModel(model_name="nonexistent_model_xyz")
        model.model_path = "/tmp/nonexistent_model.joblib"
        assert model.load() is False
