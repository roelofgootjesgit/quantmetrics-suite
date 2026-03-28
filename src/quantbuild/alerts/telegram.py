"""Telegram alerts for trade events, reports, and operational events."""
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class TelegramAlerter:
    """Sends trading alerts via Telegram bot."""

    def __init__(self, cfg: dict[str, Any]):
        tg_cfg = cfg.get("monitoring", {}).get("telegram", {})
        self._enabled = tg_cfg.get("enabled", False)
        self._bot_token = tg_cfg.get("bot_token", "")
        self._chat_id = tg_cfg.get("chat_id", "")
        self._system_label = str(tg_cfg.get("system_label", "Trading System")).strip() or "Trading System"
        self._instance_label = str(tg_cfg.get("instance_label", "")).strip()
        self._alerts_cfg = tg_cfg.get("alerts", {})
        self._report_cfg = tg_cfg.get("report", {})
        self._bot = None

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._bot_token) and bool(self._chat_id)

    def _ensure_bot(self):
        if self._bot is None and self.enabled:
            try:
                import httpx
                self._bot = httpx.Client(
                    base_url=f"https://api.telegram.org/bot{self._bot_token}",
                    timeout=10.0,
                )
            except ImportError:
                logger.warning("httpx not installed for Telegram alerts")
                self._enabled = False

    def _send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return False
        self._ensure_bot()
        if not self._bot:
            return False
        header = f"🤖 <b>{self._system_label}</b>"
        if self._instance_label:
            header += f" • <b>{self._instance_label}</b>"
        text = f"{header}\n{text}"
        try:
            resp = self._bot.post("/sendMessage", json={
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": parse_mode,
            })
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error("Telegram send failed: %s", e)
            return False

    def alert_trade_entry(self, direction: str, symbol: str, entry_price: float,
                          sl: float, tp: float, reason: str = "") -> bool:
        if not self._alerts_cfg.get("trade_entry", True):
            return False
        emoji = "🟢" if direction == "LONG" else "🔴"
        text = (
            f"{emoji} <b>TRADE OPENED</b>\n"
            f"<b>{direction}</b> {symbol} @ {entry_price:.2f}\n"
            f"SL: {sl:.2f} | TP: {tp:.2f}\n"
        )
        if reason:
            text += f"Reason: {reason}\n"
        text += f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        return self._send(text)

    def alert_trade_exit(self, direction: str, symbol: str, entry_price: float,
                         exit_price: float, profit_r: float, result: str) -> bool:
        if not self._alerts_cfg.get("trade_exit", True):
            return False
        emoji = "✅" if result == "WIN" else "❌"
        text = (
            f"{emoji} <b>TRADE CLOSED ({result})</b>\n"
            f"{direction} {symbol}: {entry_price:.2f} → {exit_price:.2f}\n"
            f"P&L: {profit_r:+.2f}R\n"
            f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )
        return self._send(text)

    def alert_news_event(self, headline: str, source: str, sentiment: str,
                         impact: float, classification: str = "") -> bool:
        if not self._alerts_cfg.get("news_event", True):
            return False
        emoji = "📰"
        if sentiment == "bullish":
            emoji = "🟡⬆️"
        elif sentiment == "bearish":
            emoji = "🟡⬇️"
        text = (
            f"{emoji} <b>NEWS EVENT</b>\n"
            f"<b>{headline[:100]}</b>\n"
            f"Source: {source} | Sentiment: {sentiment} ({impact:+.2f})\n"
        )
        if classification:
            text += f"Type: {classification}\n"
        return self._send(text)

    def alert_counter_news(self, trade_id: str, direction: str,
                           headline: str, action: str) -> bool:
        if not self._alerts_cfg.get("counter_news", True):
            return False
        emoji = "⚠️" if action == "warn" else "🚨"
        text = (
            f"{emoji} <b>COUNTER-NEWS DETECTED</b>\n"
            f"Position: {trade_id} ({direction})\n"
            f"News: {headline[:100]}\n"
            f"Action: <b>{action.upper()}</b>"
        )
        return self._send(text)

    def alert_daily_summary(self, trades_today: int, pnl_r: float,
                            open_positions: int, news_events: int) -> bool:
        if not self._alerts_cfg.get("daily_summary", True):
            return False
        emoji = "📊"
        text = (
            f"{emoji} <b>DAILY SUMMARY</b>\n"
            f"Trades: {trades_today} | P&L: {pnl_r:+.2f}R\n"
            f"Open positions: {open_positions}\n"
            f"News events processed: {news_events}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        return self._send(text)

    def report_interval_seconds(self, default_seconds: int = 3600) -> int:
        raw = self._report_cfg.get("interval_seconds", default_seconds)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default_seconds
        return max(60, value)

    def startup_report_enabled(self) -> bool:
        return bool(self._report_cfg.get("on_startup", True))

    def shutdown_report_enabled(self) -> bool:
        return bool(self._report_cfg.get("on_shutdown", True))

    def status_report_enabled(self) -> bool:
        return bool(self._alerts_cfg.get("status_report", True))

    def alert_status_report(
        self,
        symbol: str,
        mode: str,
        regime: str,
        trades_today: int,
        pnl_r: float,
        open_positions: int,
        source: str = "unknown",
        broker_positions: int | None = None,
        account_daily_pnl: float | None = None,
        account_daily_baseline_at: str | None = None,
        account_balance: float | None = None,
        account_equity: float | None = None,
        account_unrealized_pnl: float | None = None,
        account_currency: str = "USD",
    ) -> bool:
        if not self.status_report_enabled():
            return False
        if broker_positions is None:
            positions_line = f"Active trades: {open_positions}"
        else:
            positions_line = f"Active trades: {open_positions} tracked / {broker_positions} broker"
        account_lines = ""
        if account_daily_pnl is not None:
            account_lines += f"Account P/L today: {account_daily_pnl:+,.2f} {account_currency}\n"
        if account_daily_baseline_at:
            account_lines += f"Daily baseline: {account_daily_baseline_at}\n"
        if account_balance is not None:
            account_lines += f"Account balance: {account_balance:,.2f} {account_currency}\n"
        if account_equity is not None:
            account_lines += f"Account equity: {account_equity:,.2f} {account_currency}\n"
        if account_unrealized_pnl is not None:
            account_lines += f"Account P/L (float): {account_unrealized_pnl:+,.2f} {account_currency}\n"
        text = (
            f"📡 <b>STATUS REPORT</b>\n"
            f"Configured symbol: {symbol}\n"
            f"Mode: {mode}\n"
            f"Regime: {regime}\n"
            f"Trades today: {trades_today}\n"
            f"P&L today: {pnl_r:+.2f}R\n"
            f"{positions_line}\n"
            f"{account_lines}"
            f"Data source: {source}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        return self._send(text)

    def alert_error(self, error_type: str, message: str) -> bool:
        if not self._alerts_cfg.get("error_alerts", True):
            return False
        text = (
            f"🚫 <b>ERROR: {error_type}</b>\n"
            f"{message[:500]}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )
        return self._send(text)
