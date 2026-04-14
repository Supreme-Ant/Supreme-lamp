"""Telegram bot for notifications and commands."""

import logging
import threading
from typing import Optional, Callable

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Sends trading alerts and accepts commands via Telegram Bot API.

    Notifications:
    - Trade execution alerts (entry/exit with PnL)
    - Signal generation alerts
    - Risk warnings (drawdown, stop-loss triggers)
    - Daily summary reports

    Commands (processed via polling):
    - /status - Bot status overview
    - /balance - Current balance
    - /positions - Open positions
    - /pnl - Today's PnL
    - /trades - Recent trades
    - /stop - Pause trading
    - /start - Resume trading
    - /help - Command list
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._command_handlers: dict[str, Callable] = {}
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._last_update_id = 0

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured chat."""
        if not self.is_configured:
            logger.debug("Telegram not configured, skipping message")
            return False

        try:
            resp = requests.post(
                f"{self._base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if resp.ok:
                return True
            else:
                logger.error("Telegram send failed: %s", resp.text)
                return False
        except requests.RequestException as e:
            logger.error("Telegram send error: %s", e)
            return False

    def notify_trade(self, side: str, symbol: str, amount: float,
                     price: float, cost: float, strategy: str,
                     is_paper: bool = True, stop_loss: float = None,
                     take_profit: float = None) -> bool:
        """Send a trade execution notification."""
        mode = "PAPER" if is_paper else "LIVE"
        emoji = "🟢" if side == "buy" else "🔴"
        msg = (
            f"{emoji} <b>{mode} | {side.upper()} {symbol}</b>\n"
            f"Amount: {amount:.6f}\n"
            f"Price: ${price:,.2f}\n"
            f"Cost: ${cost:,.2f} USDT\n"
            f"Strategy: {strategy}"
        )
        if stop_loss:
            msg += f"\nSL: ${stop_loss:,.2f}"
        if take_profit:
            msg += f" | TP: ${take_profit:,.2f}"
        return self.send(msg)

    def notify_position_closed(self, symbol: str, entry_price: float,
                               exit_price: float, pnl: float) -> bool:
        """Send position closed notification."""
        emoji = "💰" if pnl >= 0 else "💸"
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        return self.send(
            f"{emoji} <b>Position CLOSED: {symbol}</b>\n"
            f"Entry: ${entry_price:,.2f} → Exit: ${exit_price:,.2f}\n"
            f"PnL: <b>{'+' if pnl >= 0 else ''}{pnl:.2f} USDT ({pnl_pct:+.1f}%)</b>"
        )

    def notify_stop_loss(self, symbol: str, price: float,
                         pnl: float) -> bool:
        """Send stop-loss trigger notification."""
        return self.send(
            f"🛑 <b>STOP-LOSS TRIGGERED</b>\n"
            f"Symbol: {symbol}\n"
            f"Price: ${price:,.2f}\n"
            f"Loss: {pnl:.2f} USDT"
        )

    def notify_signal(self, symbol: str, action: str, confidence: float,
                      ta_score: float, ml_score: float) -> bool:
        """Send AI signal notification."""
        emoji = "📈" if action == "buy" else "📉" if action == "sell" else "➡️"
        return self.send(
            f"{emoji} <b>AI Signal: {action.upper()} {symbol}</b>\n"
            f"Confidence: {confidence:.1%}\n"
            f"TA Score: {ta_score:.2f} | ML Score: {ml_score:.2f}"
        )

    def notify_daily_summary(self, total_value: float, daily_pnl: float,
                             total_pnl: float, num_trades: int,
                             num_positions: int) -> bool:
        """Send daily summary report."""
        pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
        return self.send(
            f"📊 <b>Daily Summary</b>\n"
            f"{'─' * 20}\n"
            f"Portfolio: ${total_value:,.2f}\n"
            f"{pnl_emoji} Daily PnL: {'+' if daily_pnl >= 0 else ''}{daily_pnl:.2f} USDT\n"
            f"Total PnL: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} USDT\n"
            f"Trades today: {num_trades}\n"
            f"Open positions: {num_positions}"
        )

    def notify_error(self, error_msg: str) -> bool:
        """Send error notification."""
        return self.send(f"⚠️ <b>Bot Error</b>\n{error_msg}")

    def notify_risk_warning(self, warning: str) -> bool:
        """Send risk management warning."""
        return self.send(f"🚨 <b>Risk Warning</b>\n{warning}")

    # ── Command handling ─────────────────────────────

    def register_command(self, command: str, handler: Callable):
        """Register a command handler (e.g., /status -> status_handler)."""
        self._command_handlers[command.lstrip("/")] = handler

    def start_polling(self):
        """Start polling for incoming commands in a background thread."""
        if not self.is_configured:
            logger.warning("Telegram not configured, command polling disabled")
            return

        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        logger.info("Telegram command polling started")

    def stop_polling(self):
        """Stop the polling loop."""
        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
        logger.info("Telegram command polling stopped")

    def _poll_loop(self):
        """Main polling loop for incoming messages."""
        while self._polling:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle_update(update)
            except Exception as e:
                logger.error("Telegram polling error: %s", e)
            # Polling interval handled by long polling timeout

    def _get_updates(self) -> list:
        """Fetch new updates from Telegram."""
        try:
            resp = requests.get(
                f"{self._base_url}/getUpdates",
                params={
                    "offset": self._last_update_id + 1,
                    "timeout": 30,  # Long polling
                    "allowed_updates": ["message"],
                },
                timeout=35,
            )
            if resp.ok:
                data = resp.json()
                return data.get("result", [])
        except requests.RequestException:
            pass
        return []

    def _handle_update(self, update: dict):
        """Process a single update from Telegram."""
        self._last_update_id = update.get("update_id", self._last_update_id)

        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Only respond to our configured chat
        if chat_id != self.chat_id:
            return

        if not text.startswith("/"):
            return

        # Parse command
        parts = text.split()
        command = parts[0].lstrip("/").split("@")[0]  # Handle @botname suffix
        args = parts[1:]

        if command in self._command_handlers:
            try:
                response = self._command_handlers[command](*args)
                if response:
                    self.send(str(response))
            except Exception as e:
                logger.error("Command /%s error: %s", command, e)
                self.send(f"Error executing /{command}: {e}")
        elif command == "help":
            self._send_help()
        else:
            self.send(f"Unknown command: /{command}\nType /help for available commands.")

    def _send_help(self):
        """Send help message with available commands."""
        commands = "\n".join(f"/{cmd}" for cmd in sorted(self._command_handlers.keys()))
        self.send(
            f"🤖 <b>Trading Bot Commands</b>\n"
            f"{'─' * 20}\n"
            f"{commands}\n"
            f"/help - Show this help"
        )
