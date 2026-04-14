"""Technical indicator feature extraction for AI trading signals."""

import logging
import pandas as pd
import numpy as np
from ta import trend, momentum, volatility, volume

logger = logging.getLogger(__name__)


class FeatureEngine:
    """
    Extracts technical analysis features from OHLCV data.
    Uses the 'ta' library for indicator computation.
    """

    @staticmethod
    def ohlcv_to_dataframe(ohlcv_data: list) -> pd.DataFrame:
        """Convert ccxt OHLCV data to a pandas DataFrame."""
        df = pd.DataFrame(
            ohlcv_data,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    @staticmethod
    def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all technical indicators on OHLCV DataFrame.
        Returns enriched DataFrame with indicator columns.
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]
        vol = df["volume"]

        # ── Trend Indicators ──────────────────────────────
        # Moving Averages
        df["ema_9"] = trend.ema_indicator(close, window=9)
        df["ema_21"] = trend.ema_indicator(close, window=21)
        df["ema_50"] = trend.ema_indicator(close, window=50)
        df["sma_20"] = trend.sma_indicator(close, window=20)
        df["sma_50"] = trend.sma_indicator(close, window=50)

        # MACD
        macd = trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_hist"] = macd.macd_diff()

        # ADX (Average Directional Index)
        adx = trend.ADXIndicator(high, low, close, window=14)
        df["adx"] = adx.adx()
        df["adx_pos"] = adx.adx_pos()
        df["adx_neg"] = adx.adx_neg()

        # Ichimoku
        ichimoku = trend.IchimokuIndicator(high, low, window1=9, window2=26, window3=52)
        df["ichimoku_a"] = ichimoku.ichimoku_a()
        df["ichimoku_b"] = ichimoku.ichimoku_b()

        # ── Momentum Indicators ───────────────────────────
        # RSI
        df["rsi_14"] = momentum.rsi(close, window=14)
        df["rsi_7"] = momentum.rsi(close, window=7)

        # Stochastic Oscillator
        stoch = momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()

        # Williams %R
        df["williams_r"] = momentum.williams_r(high, low, close, lbp=14)

        # ROC (Rate of Change)
        df["roc"] = momentum.roc(close, window=12)

        # ── Volatility Indicators ─────────────────────────
        # Bollinger Bands
        bb = volatility.BollingerBands(close, window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_width"] = bb.bollinger_wband()
        df["bb_pct"] = bb.bollinger_pband()

        # ATR (Average True Range)
        df["atr"] = volatility.average_true_range(high, low, close, window=14)

        # ── Volume Indicators ─────────────────────────────
        # OBV (On-Balance Volume)
        df["obv"] = volume.on_balance_volume(close, vol)

        # Volume SMA
        df["volume_sma_20"] = vol.rolling(window=20).mean()

        # MFI (Money Flow Index)
        df["mfi"] = volume.money_flow_index(high, low, close, vol, window=14)

        return df

    @staticmethod
    def build_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Build ML-ready feature matrix from indicator-enriched DataFrame.
        Normalizes and creates derived features.
        """
        features = pd.DataFrame(index=df.index)

        # ── Price-based features ──────────────────────────
        features["price_change_1"] = df["close"].pct_change(1)
        features["price_change_3"] = df["close"].pct_change(3)
        features["price_change_5"] = df["close"].pct_change(5)
        features["price_change_10"] = df["close"].pct_change(10)

        # Price relative to moving averages
        features["price_vs_ema9"] = (df["close"] - df["ema_9"]) / df["ema_9"]
        features["price_vs_ema21"] = (df["close"] - df["ema_21"]) / df["ema_21"]
        features["price_vs_ema50"] = (df["close"] - df["ema_50"]) / df["ema_50"]
        features["price_vs_sma20"] = (df["close"] - df["sma_20"]) / df["sma_20"]

        # ── EMA crossover features ────────────────────────
        features["ema9_above_ema21"] = (df["ema_9"] > df["ema_21"]).astype(float)
        features["ema21_above_ema50"] = (df["ema_21"] > df["ema_50"]).astype(float)

        # ── MACD features ────────────────────────────────
        features["macd_hist"] = df["macd_hist"]
        features["macd_hist_change"] = df["macd_hist"].diff()
        features["macd_above_signal"] = (df["macd"] > df["macd_signal"]).astype(float)

        # ── RSI features ─────────────────────────────────
        features["rsi_14"] = df["rsi_14"] / 100  # Normalize to 0-1
        features["rsi_7"] = df["rsi_7"] / 100
        features["rsi_oversold"] = (df["rsi_14"] < 30).astype(float)
        features["rsi_overbought"] = (df["rsi_14"] > 70).astype(float)

        # ── Stochastic features ──────────────────────────
        features["stoch_k"] = df["stoch_k"] / 100
        features["stoch_d"] = df["stoch_d"] / 100
        features["stoch_k_above_d"] = (df["stoch_k"] > df["stoch_d"]).astype(float)

        # ── Bollinger Band features ──────────────────────
        features["bb_pct"] = df["bb_pct"]  # Already 0-1 range
        features["bb_width"] = df["bb_width"]

        # ── ADX features ─────────────────────────────────
        features["adx"] = df["adx"] / 100
        features["adx_strong_trend"] = (df["adx"] > 25).astype(float)
        features["adx_pos_above_neg"] = (df["adx_pos"] > df["adx_neg"]).astype(float)

        # ── Volatility features ──────────────────────────
        features["atr_pct"] = df["atr"] / df["close"]  # ATR as % of price

        # ── Volume features ──────────────────────────────
        features["volume_ratio"] = df["volume"] / df["volume_sma_20"]
        features["mfi"] = df["mfi"] / 100

        # ── Williams %R ──────────────────────────────────
        features["williams_r"] = df["williams_r"] / 100

        # ── ROC ──────────────────────────────────────────
        features["roc"] = df["roc"]

        # Drop any NaN rows (from indicator warm-up periods)
        features = features.dropna()

        return features

    @staticmethod
    def create_labels(df: pd.DataFrame, lookahead: int = 5, threshold: float = 0.01) -> pd.Series:
        """
        Create binary labels for ML training.
        1 = price goes up by more than threshold in next N candles
        0 = price goes down or stays flat

        Args:
            df: DataFrame with 'close' column
            lookahead: Number of candles to look ahead
            threshold: Minimum price change to count as positive (1%)
        """
        future_return = df["close"].shift(-lookahead) / df["close"] - 1
        labels = (future_return > threshold).astype(int)
        return labels

    @staticmethod
    def generate_ta_score(df: pd.DataFrame) -> float:
        """
        Rule-based technical analysis score (0.0 = strong sell, 1.0 = strong buy).
        Uses the latest row of the indicator-enriched DataFrame.
        """
        if df.empty:
            return 0.5

        latest = df.iloc[-1]
        score = 0.0
        total_weight = 0.0

        # RSI signal (weight: 2)
        rsi = latest.get("rsi_14", 50)
        if rsi < 30:
            score += 2.0  # Oversold = buy signal
        elif rsi > 70:
            score += 0.0  # Overbought = sell signal
        else:
            score += 1.0  # Neutral
        total_weight += 2.0

        # MACD signal (weight: 2)
        macd_hist = latest.get("macd_hist", 0)
        if macd_hist > 0:
            score += 2.0  # Bullish
        else:
            score += 0.0  # Bearish
        total_weight += 2.0

        # EMA alignment (weight: 1.5)
        ema9 = latest.get("ema_9", 0)
        ema21 = latest.get("ema_21", 0)
        ema50 = latest.get("ema_50", 0)
        if ema9 > ema21 > ema50:
            score += 1.5  # Golden alignment
        elif ema9 < ema21 < ema50:
            score += 0.0  # Death alignment
        else:
            score += 0.75  # Mixed
        total_weight += 1.5

        # Bollinger Band position (weight: 1)
        bb_pct = latest.get("bb_pct", 0.5)
        if bb_pct < 0.2:
            score += 1.0  # Near lower band = buy
        elif bb_pct > 0.8:
            score += 0.0  # Near upper band = sell
        else:
            score += 0.5
        total_weight += 1.0

        # ADX trend strength (weight: 1)
        adx = latest.get("adx", 0)
        adx_pos = latest.get("adx_pos", 0)
        adx_neg = latest.get("adx_neg", 0)
        if adx > 25 and adx_pos > adx_neg:
            score += 1.0  # Strong uptrend
        elif adx > 25 and adx_neg > adx_pos:
            score += 0.0  # Strong downtrend
        else:
            score += 0.5  # Weak/no trend
        total_weight += 1.0

        # Stochastic (weight: 1)
        stoch_k = latest.get("stoch_k", 50)
        stoch_d = latest.get("stoch_d", 50)
        if stoch_k < 20:
            score += 1.0  # Oversold
        elif stoch_k > 80:
            score += 0.0  # Overbought
        elif stoch_k > stoch_d:
            score += 0.7  # Bullish crossover
        else:
            score += 0.3
        total_weight += 1.0

        # Volume confirmation (weight: 0.5)
        vol_ratio = latest.get("volume_ratio", 1.0) if "volume_ratio" in df.columns else 1.0
        if vol_ratio > 1.5:
            score += 0.5  # High volume confirms signal
        else:
            score += 0.25
        total_weight += 0.5

        # Normalize to 0-1
        return score / total_weight if total_weight > 0 else 0.5
