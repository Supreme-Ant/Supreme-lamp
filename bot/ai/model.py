"""ML model for predicting crypto price direction."""

import logging
import os
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import cross_val_score
from sklearn.metrics import accuracy_score, f1_score, classification_report
import joblib

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")


class TradingModel:
    """
    Gradient Boosting model trained on technical indicator features
    to predict price direction (up/down) over the next N candles.
    """

    def __init__(self, model_name: str = "default"):
        self.model_name = model_name
        self.model_path = os.path.join(MODEL_DIR, f"{model_name}.joblib")
        self._model: Optional[GradientBoostingClassifier] = None
        self._feature_names: list[str] = []

        # Ensure models directory exists
        os.makedirs(MODEL_DIR, exist_ok=True)

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def train(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """
        Train the model on feature matrix X and binary labels y.

        Args:
            X: Feature DataFrame (from FeatureEngine.build_features)
            y: Binary labels (1=up, 0=down) from FeatureEngine.create_labels

        Returns:
            Dict with training metrics.
        """
        # Align X and y, drop NaN
        combined = pd.concat([X, y.rename("label")], axis=1).dropna()
        X_clean = combined.drop("label", axis=1)
        y_clean = combined["label"]

        if len(X_clean) < 50:
            raise ValueError(f"Not enough training data: {len(X_clean)} samples (need >= 50)")

        self._feature_names = list(X_clean.columns)

        logger.info(
            "Training model '%s' on %d samples with %d features",
            self.model_name, len(X_clean), len(self._feature_names),
        )

        self._model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
        )

        # Cross-validation scores
        cv_scores = cross_val_score(self._model, X_clean, y_clean, cv=5, scoring="accuracy")

        # Final fit on all data
        self._model.fit(X_clean, y_clean)

        # Training metrics
        y_pred = self._model.predict(X_clean)
        metrics = {
            "accuracy": accuracy_score(y_clean, y_pred),
            "f1": f1_score(y_clean, y_pred, zero_division=0),
            "cv_accuracy_mean": cv_scores.mean(),
            "cv_accuracy_std": cv_scores.std(),
            "samples": len(X_clean),
            "features": len(self._feature_names),
            "class_distribution": {
                "up": int(y_clean.sum()),
                "down": int(len(y_clean) - y_clean.sum()),
            },
        }

        # Save model
        self.save()

        logger.info(
            "Model trained: accuracy=%.3f, cv=%.3f (+/- %.3f), f1=%.3f",
            metrics["accuracy"], metrics["cv_accuracy_mean"],
            metrics["cv_accuracy_std"], metrics["f1"],
        )

        return metrics

    def predict(self, X: pd.DataFrame) -> dict:
        """
        Predict price direction for feature data.

        Returns:
            {
                "direction": "buy" or "sell",
                "confidence": float (0-1),
                "probabilities": {"up": float, "down": float},
            }
        """
        if not self.is_trained:
            raise RuntimeError("Model not trained. Call train() or load() first.")

        # Ensure feature alignment
        X_aligned = self._align_features(X)

        if len(X_aligned) == 0:
            return {"direction": "hold", "confidence": 0.0, "probabilities": {"up": 0.5, "down": 0.5}}

        # Get the latest row for prediction
        latest = X_aligned.iloc[[-1]]

        proba = self._model.predict_proba(latest)[0]
        # proba[0] = P(down), proba[1] = P(up)
        up_prob = proba[1] if len(proba) > 1 else proba[0]
        down_prob = 1 - up_prob

        if up_prob > 0.5:
            direction = "buy"
            confidence = up_prob
        else:
            direction = "sell"
            confidence = down_prob

        return {
            "direction": direction,
            "confidence": confidence,
            "probabilities": {"up": up_prob, "down": down_prob},
        }

    def predict_proba_up(self, X: pd.DataFrame) -> float:
        """Return probability of upward price movement for the latest data point."""
        result = self.predict(X)
        return result["probabilities"]["up"]

    def get_feature_importance(self) -> dict:
        """Get feature importance rankings."""
        if not self.is_trained:
            return {}
        importances = self._model.feature_importances_
        return dict(
            sorted(
                zip(self._feature_names, importances),
                key=lambda x: x[1],
                reverse=True,
            )
        )

    def save(self):
        """Save model to disk."""
        if not self.is_trained:
            raise RuntimeError("No model to save.")
        data = {
            "model": self._model,
            "feature_names": self._feature_names,
            "model_name": self.model_name,
        }
        joblib.dump(data, self.model_path)
        logger.info("Model saved to %s", self.model_path)

    def load(self) -> bool:
        """Load model from disk. Returns True if successful."""
        if not os.path.exists(self.model_path):
            logger.warning("Model file not found: %s", self.model_path)
            return False
        try:
            data = joblib.load(self.model_path)
            self._model = data["model"]
            self._feature_names = data["feature_names"]
            self.model_name = data.get("model_name", self.model_name)
            logger.info("Model loaded from %s", self.model_path)
            return True
        except Exception as e:
            logger.error("Failed to load model: %s", e)
            return False

    def _align_features(self, X: pd.DataFrame) -> pd.DataFrame:
        """Align input features with training features."""
        missing = set(self._feature_names) - set(X.columns)
        if missing:
            logger.warning("Missing features in prediction data: %s", missing)
            for col in missing:
                X[col] = 0.0
        return X[self._feature_names].dropna()
