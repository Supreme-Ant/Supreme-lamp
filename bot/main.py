"""
Main entry point for the AI Crypto Copy-Trading Bot.

Bootstrap sequence:
1. Load configuration from .env
2. Initialize database
3. Create exchange client (live or paper based on config)
4. Initialize all managers (risk, portfolio, order)
5. Initialize all strategies (copy trader, signal follower, AI trader)
6. Set up Telegram notifications with command handlers
7. Set up scheduler for periodic tasks
8. Start FastAPI dashboard in a background thread
9. Start the scheduler
10. Block on main thread, handle graceful shutdown
"""

import logging
import signal
import sys
import threading
import time
from datetime import datetime

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from cryptography.fernet import Fernet

from config.settings import settings
from bot.database.db import init_db, get_session
from bot.exchange.client import ExchangeClient
from bot.exchange.paper_trader import PaperTrader
from bot.exchange.order_manager import OrderManager
from bot.risk.manager import RiskManager
from bot.portfolio.tracker import PortfolioTracker
from bot.strategies.copy_trader import CopyTrader
from bot.strategies.signal_follower import SignalFollower
from bot.strategies.ai_trader import AITrader
from bot.notifications.telegram import TelegramNotifier
from bot.dashboard.app import create_dashboard

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("trading_bot.log", mode="a"),
    ],
)
logger = logging.getLogger("bot")

# Global shutdown event
_shutdown = threading.Event()


def main():
    """Start the trading bot."""
    logger.info("=" * 60)
    logger.info("AI CRYPTO COPY-TRADING BOT")
    logger.info("Mode: %s", settings.trading_mode.upper())
    logger.info("=" * 60)

    # ── 1. Initialize Database ────────────────────────
    init_db(settings.database_url)
    logger.info("Database initialized")

    # ── 2. Auto-generate encryption key if needed ─────
    if not settings.encryption_key:
        key = Fernet.generate_key().decode()
        logger.warning(
            "No ENCRYPTION_KEY set. Generated: %s\n"
            "Add this to your .env file to persist across restarts.",
            key,
        )
        settings.encryption_key = key

    # ── 3. Create Exchange Client ─────────────────────
    if settings.is_paper_mode:
        exchange_client = PaperTrader(initial_balance_usdt=10000.0)
        is_paper = True
        logger.info("Paper trading mode - starting with $10,000 USDT")
    else:
        if not settings.binance.api_key or settings.binance.api_key == "your_api_key_here":
            logger.error("Binance API key not configured! Set BINANCE_API_KEY in .env")
            sys.exit(1)
        exchange_client = ExchangeClient(
            api_key=settings.binance.api_key,
            api_secret=settings.binance.api_secret,
            testnet=settings.binance.testnet,
        )
        is_paper = False
        logger.info("LIVE trading mode")

    # Connect to exchange
    if not exchange_client.connect():
        logger.error("Failed to connect to exchange. Exiting.")
        sys.exit(1)

    # ── 4. Initialize Managers ────────────────────────
    risk_manager = RiskManager(
        max_position_size_pct=settings.trading.max_position_size_pct,
        max_positions=settings.trading.max_positions,
        daily_loss_limit_pct=settings.trading.daily_loss_limit_pct,
        stop_loss_pct=settings.trading.stop_loss_pct,
        take_profit_pct=settings.trading.take_profit_pct,
        trailing_stop_pct=settings.trading.trailing_stop_pct,
    )

    # Set initial peak balance
    balance = exchange_client.get_balance()
    initial_balance = balance.get("USDT", {}).get("total", 10000)
    risk_manager.update_peak_balance(initial_balance)

    # Telegram notifier
    notifier = TelegramNotifier(
        bot_token=settings.telegram.bot_token,
        chat_id=settings.telegram.chat_id,
    )

    # Order manager
    order_manager = OrderManager(
        exchange_client=exchange_client,
        risk_manager=risk_manager,
        notifier=notifier,
        is_paper=is_paper,
    )

    # Portfolio tracker
    portfolio_tracker = PortfolioTracker(
        exchange_client=exchange_client,
        is_paper=is_paper,
    )

    # ── 5. Initialize Strategies ──────────────────────
    copy_trader = CopyTrader(
        order_manager=order_manager,
        exchange_client=exchange_client,
        risk_manager=risk_manager,
        notifier=notifier,
        trade_ratio=settings.copy_trading.trade_ratio,
    )

    signal_follower = SignalFollower(
        order_manager=order_manager,
        exchange_client=exchange_client,
        risk_manager=risk_manager,
        notifier=notifier,
        default_amount_usdt=settings.trading.default_amount_usdt,
    )

    ai_trader = AITrader(
        order_manager=order_manager,
        exchange_client=exchange_client,
        risk_manager=risk_manager,
        notifier=notifier,
        symbols=settings.ai.symbols,
        timeframes=settings.ai.timeframes,
        confidence_threshold=settings.ai.confidence_threshold,
        default_amount_usdt=settings.trading.default_amount_usdt,
        retrain_hours=settings.ai.retrain_hours,
        lookback_days=settings.ai.lookback_days,
    )

    # ── 6. Setup Telegram Commands ────────────────────
    _setup_telegram_commands(
        notifier, portfolio_tracker, risk_manager,
        copy_trader, signal_follower, ai_trader, is_paper,
    )

    # ── 7. Setup Scheduler ────────────────────────────
    scheduler = _setup_scheduler(
        exchange_client, risk_manager, portfolio_tracker,
        order_manager, copy_trader, signal_follower, ai_trader,
    )

    # ── 8. Start Dashboard ────────────────────────────
    dashboard = create_dashboard(
        portfolio_tracker=portfolio_tracker,
        order_manager=order_manager,
        risk_manager=risk_manager,
        copy_trader=copy_trader,
        signal_follower=signal_follower,
        ai_trader=ai_trader,
        notifier=notifier,
    )

    dashboard_thread = threading.Thread(
        target=_run_dashboard,
        args=(dashboard, settings.dashboard.host, settings.dashboard.port),
        daemon=True,
    )
    dashboard_thread.start()
    logger.info(
        "Dashboard started at http://%s:%d",
        settings.dashboard.host, settings.dashboard.port,
    )

    # ── 9. Start Everything ───────────────────────────
    scheduler.start()
    logger.info("Scheduler started with all jobs")

    if notifier.is_configured:
        notifier.start_polling()
        notifier.send(
            f"🚀 <b>Trading Bot Started</b>\n"
            f"Mode: {'PAPER' if is_paper else 'LIVE'}\n"
            f"Balance: ${initial_balance:,.2f} USDT\n"
            f"Dashboard: http://{settings.dashboard.host}:{settings.dashboard.port}"
        )
    else:
        logger.warning("Telegram not configured - no notifications will be sent")

    # Take initial portfolio snapshot
    portfolio_tracker.take_snapshot()

    logger.info("Bot is running. Press Ctrl+C to stop.")

    # ── 10. Wait for Shutdown ─────────────────────────
    def handle_shutdown(signum, frame):
        logger.info("Shutdown signal received...")
        _shutdown.set()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        while not _shutdown.is_set():
            _shutdown.wait(timeout=1)
    except KeyboardInterrupt:
        pass

    # ── Cleanup ───────────────────────────────────────
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    notifier.stop_polling()

    if notifier.is_configured:
        notifier.send("🛑 <b>Trading Bot Stopped</b>")

    # Final snapshot
    portfolio_tracker.take_snapshot()
    logger.info("Bot stopped. Goodbye!")


def _setup_telegram_commands(notifier, portfolio_tracker, risk_manager,
                             copy_trader, signal_follower, ai_trader, is_paper):
    """Register Telegram bot command handlers."""

    def cmd_status():
        mode = "PAPER" if is_paper else "LIVE"
        summary = portfolio_tracker.get_summary()
        risk = risk_manager.get_risk_status()
        return (
            f"🤖 <b>Bot Status</b>\n"
            f"Mode: {mode}\n"
            f"Balance: ${summary['total_value_usdt']:,.2f}\n"
            f"Positions: {summary['num_positions']}/{risk['max_positions']}\n"
            f"Daily PnL: {'+' if summary['daily_pnl'] >= 0 else ''}"
            f"${summary['daily_pnl']:.2f}\n"
            f"AI: {'ON' if ai_trader.is_active else 'OFF'} | "
            f"Copy: {'ON' if copy_trader.is_active else 'OFF'} | "
            f"Signals: {'ON' if signal_follower.is_active else 'OFF'}"
        )

    def cmd_balance():
        summary = portfolio_tracker.get_summary()
        lines = [f"💰 <b>Balance</b>\nTotal: ${summary['total_value_usdt']:,.2f}"]
        for cur, info in summary.get("balances", {}).items():
            if info.get("total", 0) > 0:
                lines.append(f"  {cur}: {info['total']:.8f}")
        return "\n".join(lines)

    def cmd_positions():
        positions = portfolio_tracker.get_open_positions()
        if not positions:
            return "No open positions."
        lines = ["📊 <b>Open Positions</b>"]
        for p in positions:
            pnl_str = f"{'+' if p['unrealized_pnl'] >= 0 else ''}{p['unrealized_pnl']:.2f}"
            lines.append(
                f"\n{p['symbol']} {p['side'].upper()}\n"
                f"  Entry: {p['entry_price']:.4f} → Now: {p['current_price']:.4f}\n"
                f"  PnL: {pnl_str} ({p['unrealized_pnl_pct']:+.1f}%)"
            )
        return "\n".join(lines)

    def cmd_pnl():
        summary = portfolio_tracker.get_summary()
        return (
            f"📈 <b>PnL Report</b>\n"
            f"Daily: {'+' if summary['daily_pnl'] >= 0 else ''}"
            f"${summary['daily_pnl']:.2f}\n"
            f"Total: {'+' if summary['total_pnl'] >= 0 else ''}"
            f"${summary['total_pnl']:.2f}\n"
            f"Unrealized: {'+' if summary['unrealized_pnl'] >= 0 else ''}"
            f"${summary['unrealized_pnl']:.2f}"
        )

    def cmd_trades():
        trades = portfolio_tracker.get_trade_history(limit=5)
        if not trades:
            return "No recent trades."
        lines = ["📋 <b>Recent Trades</b>"]
        for t in trades:
            lines.append(
                f"\n{t['side'].upper()} {t['symbol']}"
                f" @ {t['price']:.4f} ({t['strategy']})"
            )
        return "\n".join(lines)

    def cmd_stop():
        ai_trader.stop()
        copy_trader.stop()
        signal_follower.stop()
        return "⏸ All strategies stopped."

    def cmd_start():
        ai_trader.start()
        copy_trader.start()
        signal_follower.start()
        return "▶️ All strategies started."

    notifier.register_command("status", cmd_status)
    notifier.register_command("balance", cmd_balance)
    notifier.register_command("positions", cmd_positions)
    notifier.register_command("pnl", cmd_pnl)
    notifier.register_command("trades", cmd_trades)
    notifier.register_command("stop", cmd_stop)
    notifier.register_command("start", cmd_start)


def _setup_scheduler(exchange_client, risk_manager, portfolio_tracker,
                     order_manager, copy_trader, signal_follower, ai_trader):
    """Configure the APScheduler with all periodic jobs."""
    scheduler = BackgroundScheduler()

    # AI Trading - run every 60 minutes
    scheduler.add_job(
        _run_strategy,
        trigger="interval",
        minutes=60,
        args=[ai_trader, "AI"],
        id="ai_trading",
        max_instances=1,
        next_run_time=datetime.utcnow(),  # Run immediately on start
    )

    # Copy Trading - poll every 30 seconds
    scheduler.add_job(
        _run_strategy,
        trigger="interval",
        seconds=settings.copy_trading.poll_interval_sec,
        args=[copy_trader, "Copy"],
        id="copy_trading",
        max_instances=1,
    )

    # Signal Following - process queue every 10 seconds
    scheduler.add_job(
        _run_strategy,
        trigger="interval",
        seconds=10,
        args=[signal_follower, "Signal"],
        id="signal_following",
        max_instances=1,
    )

    # Stop-loss/take-profit check - every 15 seconds
    scheduler.add_job(
        _check_stop_loss,
        trigger="interval",
        seconds=15,
        args=[risk_manager, exchange_client, order_manager],
        id="stop_loss_check",
        max_instances=1,
    )

    # Portfolio snapshot - every 15 minutes
    scheduler.add_job(
        portfolio_tracker.take_snapshot,
        trigger="interval",
        minutes=15,
        id="portfolio_snapshot",
    )

    # Position price update - every 30 seconds
    scheduler.add_job(
        portfolio_tracker.update_positions,
        trigger="interval",
        seconds=30,
        id="position_update",
    )

    # Peak balance update - every 5 minutes
    scheduler.add_job(
        _update_peak_balance,
        trigger="interval",
        minutes=5,
        args=[risk_manager, exchange_client],
        id="peak_balance_update",
    )

    # Paper trader: check pending limit orders - every 10 seconds
    if isinstance(exchange_client, PaperTrader):
        scheduler.add_job(
            exchange_client.check_pending_orders,
            trigger="interval",
            seconds=10,
            id="paper_pending_orders",
            max_instances=1,
        )

    return scheduler


def _run_strategy(strategy, name: str):
    """Safely run a strategy cycle."""
    try:
        orders = strategy.run()
        if orders:
            logger.info("[%s] Placed %d orders", name, len(orders))
    except Exception as e:
        logger.error("[%s] Strategy error: %s", name, e)


def _check_stop_loss(risk_manager, exchange_client, order_manager):
    """Check positions for stop-loss/take-profit triggers."""
    try:
        triggered = risk_manager.check_stop_loss_take_profit(exchange_client)
        for position in triggered:
            try:
                order_manager.close_position(position["position_id"])
                logger.info(
                    "Position %s closed: %s (PnL: %.2f)",
                    position["position_id"],
                    position["reason"],
                    position.get("unrealized_pnl", 0),
                )
            except Exception as e:
                logger.error("Failed to close position %s: %s", position["position_id"], e)
    except Exception as e:
        logger.error("Stop-loss check error: %s", e)


def _update_peak_balance(risk_manager, exchange_client):
    """Update the peak balance for drawdown tracking."""
    try:
        balance = exchange_client.get_balance()
        total = balance.get("USDT", {}).get("total", 0)
        risk_manager.update_peak_balance(total)
    except Exception as e:
        logger.error("Peak balance update error: %s", e)


def _run_dashboard(app, host: str, port: int):
    """Run the FastAPI dashboard in a thread."""
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
