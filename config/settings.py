"""Central configuration loader for the trading bot."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _get_env_float(key: str, default: float = 0.0) -> float:
    return float(os.getenv(key, str(default)))


def _get_env_int(key: str, default: int = 0) -> int:
    return int(os.getenv(key, str(default)))


def _get_env_bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")


def _get_env_list(key: str, default: str = "") -> list[str]:
    val = os.getenv(key, default)
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


@dataclass
class BinanceConfig:
    api_key: str = field(default_factory=lambda: _get_env("BINANCE_API_KEY"))
    api_secret: str = field(default_factory=lambda: _get_env("BINANCE_API_SECRET"))
    testnet: bool = field(default_factory=lambda: _get_env_bool("BINANCE_TESTNET", True))


@dataclass
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: _get_env("TELEGRAM_BOT_TOKEN"))
    chat_id: str = field(default_factory=lambda: _get_env("TELEGRAM_CHAT_ID"))
    signal_channels: list[str] = field(
        default_factory=lambda: _get_env_list("TELEGRAM_SIGNAL_CHANNELS")
    )


@dataclass
class TradingConfig:
    default_amount_usdt: float = field(
        default_factory=lambda: _get_env_float("DEFAULT_TRADE_AMOUNT_USDT", 100)
    )
    max_positions: int = field(
        default_factory=lambda: _get_env_int("MAX_POSITIONS", 5)
    )
    max_position_size_pct: float = field(
        default_factory=lambda: _get_env_float("MAX_POSITION_SIZE_PCT", 10)
    )
    daily_loss_limit_pct: float = field(
        default_factory=lambda: _get_env_float("DAILY_LOSS_LIMIT_PCT", 5)
    )
    stop_loss_pct: float = field(
        default_factory=lambda: _get_env_float("STOP_LOSS_PCT", 3)
    )
    take_profit_pct: float = field(
        default_factory=lambda: _get_env_float("TAKE_PROFIT_PCT", 6)
    )
    trailing_stop_pct: float = field(
        default_factory=lambda: _get_env_float("TRAILING_STOP_PCT", 2)
    )


@dataclass
class AIConfig:
    confidence_threshold: float = field(
        default_factory=lambda: _get_env_float("AI_CONFIDENCE_THRESHOLD", 0.7)
    )
    retrain_hours: int = field(
        default_factory=lambda: _get_env_int("AI_RETRAIN_HOURS", 24)
    )
    lookback_days: int = field(
        default_factory=lambda: _get_env_int("AI_LOOKBACK_DAYS", 30)
    )
    symbols: list[str] = field(
        default_factory=lambda: _get_env_list("AI_SYMBOLS", "BTC/USDT,ETH/USDT")
    )
    timeframes: list[str] = field(
        default_factory=lambda: _get_env_list("AI_TIMEFRAMES", "1h,4h")
    )


@dataclass
class CopyTradingConfig:
    trader_ids: list[str] = field(
        default_factory=lambda: _get_env_list("COPY_TRADER_IDS")
    )
    trade_ratio: float = field(
        default_factory=lambda: _get_env_float("COPY_TRADE_RATIO", 0.1)
    )
    poll_interval_sec: int = field(
        default_factory=lambda: _get_env_int("COPY_POLL_INTERVAL_SEC", 30)
    )


@dataclass
class DashboardConfig:
    host: str = field(default_factory=lambda: _get_env("DASHBOARD_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _get_env_int("DASHBOARD_PORT", 8080))
    secret_key: str = field(
        default_factory=lambda: _get_env("DASHBOARD_SECRET_KEY", "change-me")
    )


@dataclass
class Settings:
    trading_mode: str = field(
        default_factory=lambda: _get_env("TRADING_MODE", "paper")
    )
    database_url: str = field(
        default_factory=lambda: _get_env("DATABASE_URL", "sqlite:///trading_bot.db")
    )
    encryption_key: str = field(
        default_factory=lambda: _get_env("ENCRYPTION_KEY")
    )

    binance: BinanceConfig = field(default_factory=BinanceConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    copy_trading: CopyTradingConfig = field(default_factory=CopyTradingConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)

    @property
    def is_paper_mode(self) -> bool:
        return self.trading_mode.lower() == "paper"

    @property
    def is_live_mode(self) -> bool:
        return self.trading_mode.lower() == "live"


# Global settings instance
settings = Settings()
