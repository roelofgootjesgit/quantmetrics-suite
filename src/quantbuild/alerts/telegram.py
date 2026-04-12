"""Telegram alerts for trade events, reports, and operational events."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any

logger = logging.getLogger(__name__)


def format_suite_run_summary(
    cfg: dict[str, Any],
    *,
    config_path_display: str,
    execution_mode: str,
) -> str:
    """HTML snippet for suite start/stop (escaped values)."""
    broker = cfg.get("broker") or {}
    data = cfg.get("data") or {}
    sym = cfg.get("symbol", "")
    ql = cfg.get("quantlog") or {}
    st = cfg.get("strategy") or {}
    exec_g = cfg.get("execution_guards") or {}
    filt = cfg.get("filters") or {}
    if filt:
        filt_preview = ", ".join(f"{k}={filt.get(k)}" for k in sorted(filt.keys()))
        filt_line = f"Filters: <code>{escape(filt_preview[:240])}</code>"
    else:
        filt_line = "Filters: <i>(default strict)</i>"
    lines = [
        "<b>Settings</b>",
        f"Config: <code>{escape(config_path_display)}</code>",
        f"Execution: <b>{escape(execution_mode)}</b>",
        f"Symbol: <code>{escape(str(sym))}</code>",
        f"Broker: <code>{escape(str(broker.get('provider', '?')))}</code> · "
        f"env <code>{escape(str(broker.get('environment', '?')))}</code> · "
        f"instrument <code>{escape(str(broker.get('instrument', '')))}</code>",
        f"Data source: <code>{escape(str(data.get('source', '?')))}</code>",
        f"QuantLog: {'on' if ql.get('enabled') else 'off'} · "
        f"<code>{escape(str(ql.get('base_path', '')))}</code> · "
        f"run_id <code>{escape(str(ql.get('run_id', '')))}</code>",
        f"Strategy: <code>{escape(str(st.get('name', '')))}</code>",
        f"Guards: max_open=<code>{escape(str(exec_g.get('max_open_positions', '?')))}</code>",
        filt_line,
    ]
    return "\n".join(lines)


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
        abs_impact = abs(impact)
        if abs_impact >= 0.75:
            impact_label = "HIGH"
        elif abs_impact >= 0.5:
            impact_label = "MEDIUM"
        else:
            impact_label = "LOW"
        text = (
            f"{emoji} <b>NEWS IMPACT</b>\n"
            f"<b>{headline[:100]}</b>\n"
            f"Source: {source}\n"
            f"Sentiment: {sentiment} | Impact: {impact:+.2f} ({impact_label})\n"
        )
        if classification:
            text += f"Type: {classification}\n"
        text += f"Time: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
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
        *,
        hourly_no_action: dict[str, int] | None = None,
        hourly_enter: int = 0,
        activity_caption: str = "",
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
        activity_block = ""
        if activity_caption:
            na = hourly_no_action if hourly_no_action is not None else {}
            na_total = sum(na.values())
            act_lines = [
                f"<b>{activity_caption}</b>",
                f"NO_ACTION (no new trade): <b>{na_total}</b>",
            ]
            for rk, rv in sorted(na.items(), key=lambda x: (-x[1], x[0])):
                act_lines.append(f"  • <code>{rk}</code>: {rv}")
            act_lines.append(f"ENTER (opened): <b>{hourly_enter}</b>")
            activity_block = "\n".join(act_lines) + "\n\n"
        text = (
            f"📡 <b>STATUS REPORT</b>\n"
            f"{activity_block}"
            f"Symbol: {symbol}\n"
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

    def alert_suite_start(self, components: list[str], *, extra_html: str = "") -> bool:
        """QuantMetrics OS: suite came up; `components` are labels (build, bridge, log, …)."""
        if not self._alerts_cfg.get("suite_lifecycle", True):
            return False
        labels = ", ".join(f"<code>{escape(c)}</code>" for c in components) or "<i>(none listed)</i>"
        text = (
            f"▶️ <b>QUANTMETRICS SUITE START</b>\n"
            f"Components: {labels}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        if extra_html.strip():
            text += "\n\n" + extra_html.strip()
        return self._send(text)

    def alert_suite_stop(self, components: list[str], reason: str = "", *, extra_html: str = "") -> bool:
        if not self._alerts_cfg.get("suite_lifecycle", True):
            return False
        labels = ", ".join(f"<code>{escape(c)}</code>" for c in components) or "<i>(none listed)</i>"
        text = (
            f"⏹️ <b>QUANTMETRICS SUITE STOP</b>\n"
            f"Components: {labels}\n"
        )
        if reason.strip():
            text += f"Reason: {escape(reason.strip()[:300])}\n"
        text += f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        if extra_html.strip():
            text += "\n\n" + extra_html.strip()
        return self._send(text)
