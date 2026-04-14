# AI Advanced Crypto Copy-Trading Bot

A production-grade AI-powered cryptocurrency trading bot that combines **copy trading**, **Telegram signal following**, and **autonomous AI trading** with ML-based predictions. Connects to **Binance** exchange for real trading with comprehensive risk management.

## Features

- **Paper Trading Mode** - Test strategies with simulated $10,000 USDT using real market data before going live
- **Live Trading Mode** - Execute real trades on Binance with your API keys
- **Copy Trading** - Monitor and automatically replicate trades from successful traders
- **Telegram Signal Following** - Parse and execute trading signals from Telegram channels
- **AI Autonomous Trading** - ML-powered buy/sell signals using 40+ technical indicators and Gradient Boosting models
- **Risk Management** - Stop-loss, take-profit, position sizing, max drawdown circuit breaker, cooldown periods
- **Portfolio Tracking** - Real-time PnL, position monitoring, strategy performance analytics
- **Web Dashboard** - Browser-based monitoring at `http://localhost:8080`
- **Telegram Bot** - Real-time trade alerts and command interface (`/status`, `/balance`, `/positions`, `/pnl`)
- **Bank Withdrawal** - Withdraw profits to pre-linked bank accounts via exchange fiat withdrawal APIs

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/AntAnt1997/Supreme-lamp.git
cd Supreme-lamp
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your settings:

- **Required for paper trading**: No API keys needed! Works out of the box.
- **Required for live trading**: `BINANCE_API_KEY` and `BINANCE_API_SECRET`
- **Optional**: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` for notifications

### 3. Run

```bash
# Paper trading (default - safe to try!)
python -m bot.main

# Live trading (use with caution!)
# Set TRADING_MODE=live in .env first
python -m bot.main
```

### 4. Monitor

- **Web Dashboard**: Open `http://localhost:8080` in your browser
- **Telegram**: Send `/status` to your bot

## Architecture

```
bot/
├── main.py                  # Entry point - starts all services
├── exchange/
│   ├── client.py            # Binance exchange wrapper (ccxt)
│   ├── paper_trader.py      # Paper trading simulator
│   └── order_manager.py     # Order routing & management
├── strategies/
│   ├── base.py              # Base strategy interface
│   ├── copy_trader.py       # Copy top traders
│   ├── signal_follower.py   # Telegram signal parsing
│   └── ai_trader.py         # AI autonomous trading
├── ai/
│   ├── feature_engine.py    # 40+ technical indicators
│   ├── model.py             # ML model (Gradient Boosting)
│   └── signals.py           # Signal generation pipeline
├── risk/
│   └── manager.py           # All risk rules & enforcement
├── portfolio/
│   └── tracker.py           # PnL & position tracking
├── notifications/
│   └── telegram.py          # Telegram alerts & commands
├── database/
│   ├── models.py            # SQLAlchemy ORM models
│   └── db.py                # Database management
└── dashboard/
    ├── app.py               # FastAPI web dashboard
    ├── templates/index.html  # Dashboard UI
    └── static/              # CSS & JavaScript
```

## Trading Strategies

### AI Trading
The AI strategy uses a pipeline of:
1. **Data Collection** - OHLCV candlestick data from Binance
2. **Technical Indicators** - RSI, MACD, Bollinger Bands, EMA, ADX, ATR, Stochastic, OBV, MFI, and more
3. **Feature Engineering** - 30+ normalized ML features from raw indicators
4. **ML Prediction** - Gradient Boosting classifier predicts price direction
5. **Signal Generation** - Combines TA score (40%) + ML score (60%) for final signal
6. **Risk Check** - Every trade must pass the risk manager before execution

### Copy Trading
- Add trader IDs to track via dashboard or config
- Bot polls their trades every 30 seconds
- Proportionally sizes your trades based on your allocation percentage
- All copied trades go through risk management

### Signal Following
- Connects to Telegram signal channels
- Parses common signal formats: `BUY BTC/USDT @ 50000 SL: 48000 TP: 55000`
- Validates and executes through risk manager

## Risk Management

| Rule | Default | Description |
|------|---------|-------------|
| Max Position Size | 10% | Maximum % of portfolio per position |
| Max Positions | 5 | Maximum concurrent open positions |
| Stop-Loss | 3% | Automatic stop-loss on all positions |
| Take-Profit | 6% | Automatic take-profit target |
| Daily Loss Limit | 5% | Stop trading after daily loss exceeds limit |
| Max Drawdown | 15% | Circuit breaker - stops all trading |
| Cooldown | 3 losses / 60min | Pause after consecutive losses |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Bot status overview |
| `/balance` | Current portfolio balance |
| `/positions` | Open positions with PnL |
| `/pnl` | Daily and total PnL report |
| `/trades` | Recent trade history |
| `/start` | Resume all strategies |
| `/stop` | Pause all strategies |
| `/help` | Show all commands |

## Configuration

All settings are configured via the `.env` file. See `.env.example` for all available options.

Key settings:
- `TRADING_MODE` - `paper` (default) or `live`
- `BINANCE_API_KEY` / `BINANCE_API_SECRET` - Your Binance API credentials
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` - Telegram notification setup
- `AI_CONFIDENCE_THRESHOLD` - Minimum confidence for AI trades (default: 0.7)
- `MAX_POSITIONS` - Max concurrent positions (default: 5)
- `STOP_LOSS_PCT` / `TAKE_PROFIT_PCT` - Default SL/TP percentages

## Bank Withdrawal

To withdraw profits to your bank account:
1. **Link your bank account** on the Binance website (Settings > Fiat & Spot > Withdraw)
2. Use the dashboard API or code to initiate withdrawals to your pre-linked account

> **Note**: Bank accounts must be pre-linked via the exchange's web interface. The bot can trigger withdrawals to pre-linked accounts but cannot add new bank accounts programmatically.

## Testing

```bash
pip install pytest
pytest tests/ -v
```

## Tech Stack

- **Python 3.11+** - Core language
- **ccxt** - Unified crypto exchange API
- **scikit-learn** - ML model (Gradient Boosting)
- **pandas / numpy** - Data processing
- **ta** - Technical analysis indicators
- **FastAPI** - Web dashboard
- **SQLAlchemy** - Database ORM (SQLite)
- **APScheduler** - Task scheduling
- **cryptography** - API key encryption

## Risk Disclaimer

**WARNING: Cryptocurrency trading involves substantial risk of financial loss.**

- Past performance does not guarantee future results
- Always start with paper trading before risking real money
- Never invest more than you can afford to lose
- The bot's AI predictions are not financial advice
- You are solely responsible for your trading decisions
- Test thoroughly in paper mode before switching to live trading
