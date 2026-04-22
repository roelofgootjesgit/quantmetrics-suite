"""Live runner — main loop for paper/live trading with full decision kernel.

Wires together:
  1. Regime detector (updated from OHLC every bar)
  2. SQE entry signals (run_sqe_conditions)
  3. NewsGate (event blocking + sentiment boost)
  4. Execution guardrails (spread, slippage, session, position limits)
  5. Order management (trailing, BE, partial close)
  6. Position sync from broker
"""
import logging
import json
import os
import signal
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd

from src.quantbuild.config import load_config
from src.quantbuild.data.sessions import session_from_timestamp, ENTRY_SESSIONS
from src.quantbuild.alerts.telegram import TelegramAlerter
from src.quantbuild.execution.broker_factory import create_broker
from src.quantbuild.execution.quantlog_emitter import QuantLogEmitter
from src.quantbuild.execution.signal_evaluated_desk_grade import build_desk_grade_payload
from src.quantbuild.execution.signal_evaluated_payload import (
    assert_signal_evaluated_payload_complete,
    build_signal_evaluated_payload,
)
from src.quantbuild.execution.quantlog_ids import resolve_quantlog_run_id, resolve_quantlog_session_id
from src.quantbuild.quantlog_repo import resolve_quantlog_repo_path
from src.quantbuild.execution.order_manager import OrderManager
from src.quantbuild.execution.position_monitor import PositionMonitor
from src.quantbuild.execution.quantbridge import (
    BasicRiskValidator,
    CTraderAdapter,
    ExecutionRequest,
    JsonExecutionLogger,
    OandaAdapter,
    QuantBridgeEngine,
    StaticRouter,
)
from src.quantbuild.indicators.atr import atr as compute_atr, atr_ratio as compute_atr_ratio
from src.quantbuild.io.parquet_loader import load_parquet, ensure_live_data
from src.quantbuild.models.trade import Position, calculate_rr
from src.quantbuild.strategies.sqe_xauusd import (
    get_sqe_default_config,
    _compute_modules_once,
    run_sqe_conditions,
    sqe_decision_context_at_bar,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_EXPANSION, REGIME_COMPRESSION, REGIME_TREND,
)
from src.quantbuild.policy.system_mode import (
    SYSTEM_MODE_PRODUCTION,
    bypassed_filters_vs_production,
    resolve_effective_filters,
)

logger = logging.getLogger(__name__)

MIN_BARS_FOR_SIGNAL = 100
# Entry session: warn when 15m series last index is this many minutes behind wall clock (UTC).
STALE_BAR_LAG_WARN_MINUTES = 16.0


class LiveRunner:
    """Main live/paper trading loop with full decision kernel."""

    def __init__(self, cfg: Dict[str, Any], dry_run: bool = True):
        self.cfg = cfg
        self.dry_run = dry_run
        self._running = False
        self._broker_provider = str(cfg.get("broker", {}).get("provider", "ctrader")).lower()
        self._account_id: str = cfg.get("broker", {}).get("account_id", "") or f"{self._broker_provider}-default"

        self.broker = create_broker(cfg)
        self.order_manager = OrderManager(
            broker=self.broker if not dry_run else None,
            config=cfg.get("order_management"),
        )
        self.position_monitor = PositionMonitor(cfg)
        adapter = self._build_quantbridge_adapter()

        max_risk_pct = float(cfg.get("risk", {}).get("max_position_pct", 1.0))
        if max_risk_pct <= 0:
            max_risk_pct = 1.0
        self.quantbridge = QuantBridgeEngine(
            risk_validator=BasicRiskValidator(max_risk_percent=max(max_risk_pct, 2.0)),
            router=StaticRouter(
                account_adapters={
                    self._account_id: adapter,
                },
            ),
            logger_=JsonExecutionLogger(),
        )

        self._regime_detector = RegimeDetector(config=cfg.get("regime", {}))
        self._current_regime: Optional[str] = None
        self._current_atr: float = 0.0
        self._news_regime_override: Optional[str] = None
        self._last_regime_update: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._last_bar_ts: Optional[pd.Timestamp] = None

        # Guardrail config
        guard_cfg = cfg.get("execution_guards", {})
        self._max_spread_pips: float = guard_cfg.get("max_spread_pips", 5.0)
        self._max_slippage_r: float = guard_cfg.get("max_slippage_r", 0.15)
        self._max_open_positions: int = guard_cfg.get("max_open_positions", 3)
        self._max_daily_loss_r: float = cfg.get("risk", {}).get("max_daily_loss_r", 3.0)

        # Daily tracking
        self._daily_pnl_r: float = 0.0
        self._daily_date: Optional[str] = None
        self._daily_trade_count: int = 0
        self._daily_account_baseline_equity: Optional[float] = None
        self._daily_account_baseline_date: Optional[str] = None
        self._daily_account_baseline_set_at: Optional[str] = None
        self._decision_cycle_n: int = 0
        self._report_interval_seconds: int = 3600
        self._last_status_report: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._last_data_source: str = "unknown"

        # Alerts/monitoring
        self._telegram = TelegramAlerter(cfg)
        self._report_interval_seconds = self._telegram.report_interval_seconds(default_seconds=3600)
        self._hourly_no_action_counts: Counter[str] = Counter()
        self._hourly_enter_count: int = 0
        self._hourly_signal_eval_new_bar: int = 0
        self._hourly_signal_eval_same_bar: int = 0
        # Last signal_evaluated telemetry (status report + stale-bar guard).
        self._telemetry_eval_stage: Optional[str] = None
        self._telemetry_latest_bar_ts: Optional[str] = None
        self._telemetry_last_processed_bar_ts: Optional[str] = None
        self._telemetry_source_actual: Optional[str] = None
        self._stale_bar_warn_latched: bool = False
        # Desk-grade signal_evaluated: same-bar poll counts + last eval_stage string per bar timestamp.
        self._same_bar_skip_by_bar_ts: Dict[str, int] = {}
        self._eval_stage_by_bar_ts: Dict[str, str] = {}
        # P0-D: correlation for trade_closed after ENTER (trace / cycle / session).
        self._open_trade_quantlog: Dict[str, Dict[str, Any]] = {}

        # QuantLog integration
        self._quantlog: Optional[QuantLogEmitter] = None
        ql_cfg = cfg.get("quantlog", {}) or {}
        if bool(ql_cfg.get("enabled", True)):
            ql_base = Path(str(ql_cfg.get("base_path", "data/quantlog_events")))
            ql_env = str(ql_cfg.get("environment", "dry_run" if dry_run else "live"))
            run_id = resolve_quantlog_run_id(ql_cfg)
            session_id = resolve_quantlog_session_id(ql_cfg)
            self._quantlog = QuantLogEmitter(
                base_path=ql_base,
                source_component="live_runner",
                environment=ql_env,
                run_id=run_id,
                session_id=session_id,
            )
            logger.info("QuantLog emitter enabled: base_path=%s run_id=%s", ql_base, run_id)
            if resolve_quantlog_repo_path() is None:
                logger.warning(
                    "QuantLog JSONL is on, but the QuantLog repository was not found for CLI "
                    "(validate/summarize). Clone quantlogv1, set QUANTLOG_REPO_PATH or QUANTLOG_ROOT, or run "
                    "python scripts/check_quantlog_linkage.py — events will still be written."
                )

        # Filter / research toggles: resolved from `system_mode` + optional `filters:` overrides
        mode, eff_filters = resolve_effective_filters(cfg)
        self._system_mode: str = mode
        self._bypassed_by_mode: List[str] = bypassed_filters_vs_production(eff_filters)
        self._filter_regime: bool = eff_filters["regime"]
        self._filter_session: bool = eff_filters["session"]
        self._filter_cooldown: bool = eff_filters["cooldown"]
        self._filter_news: bool = eff_filters["news"]
        self._filter_position_limit: bool = eff_filters["position_limit"]
        self._filter_daily_loss: bool = eff_filters["daily_loss"]
        self._filter_spread: bool = eff_filters["spread"]
        self._research_raw_first: bool = eff_filters["research_raw_first"]
        logger.info(
            "LiveRunner system_mode=%s effective_filters=%s",
            mode,
            {k: eff_filters[k] for k in sorted(eff_filters)},
        )

        # News layer
        self._news_poller = None
        self._news_gate = None
        self._sentiment_engine = None
        self._rule_sentiment_engine = None
        self._counter_news = None
        self._relevance_filter = None
        self._news_history = None
        self._llm_advisor = None
        self._recent_news_events: list = []
        sentiment_cfg = cfg.get("news", {}).get("sentiment", {})
        news_tg_cfg = cfg.get("news", {}).get("telegram", {})
        self._news_max_events_per_poll: int = int(sentiment_cfg.get("max_events_per_poll", 12))
        self._news_max_source_tier_for_llm: int = int(sentiment_cfg.get("max_source_tier_for_llm", 2))
        self._news_max_event_age_minutes: int = int(sentiment_cfg.get("max_event_age_minutes", 20))
        self._news_telegram_enabled: bool = bool(news_tg_cfg.get("enabled", True))
        self._news_telegram_min_abs_impact: float = float(news_tg_cfg.get("min_abs_impact", 0.45))
        self._news_telegram_max_alerts_per_poll: int = int(news_tg_cfg.get("max_alerts_per_poll", 3))

        if cfg.get("news", {}).get("enabled", False):
            self._setup_news_layer()

    def _build_quantbridge_adapter(self):
        if self._broker_provider == "ctrader":
            return CTraderAdapter(self.broker)
        if self._broker_provider == "oanda":
            return OandaAdapter(self.broker)
        raise ValueError(f"Unsupported broker provider: {self._broker_provider}")

    # ── News Layer Setup ──────────────────────────────────────────────

    def _setup_news_layer(self):
        try:
            from src.quantbuild.news.poller import NewsPoller
            from src.quantbuild.news.relevance_filter import RelevanceFilter
            from src.quantbuild.news.gold_classifier import GoldEventClassifier
            from src.quantbuild.news.sentiment import HybridSentiment, RuleBasedSentiment
            from src.quantbuild.news.counter_news import CounterNewsDetector
            from src.quantbuild.news.history import NewsHistory
            from src.quantbuild.news.advisor import LLMTradeAdvisor
            from src.quantbuild.strategy_modules.news_gate import NewsGate

            self._news_poller = NewsPoller(self.cfg)
            self._news_poller.setup()
            self._relevance_filter = RelevanceFilter(self.cfg)
            self._gold_classifier = GoldEventClassifier(self.cfg)
            self._sentiment_engine = HybridSentiment(self.cfg)
            self._rule_sentiment_engine = RuleBasedSentiment()
            self._counter_news = CounterNewsDetector(self.cfg)
            self._news_gate = NewsGate(self.cfg)
            self._news_history = NewsHistory()
            self._llm_advisor = LLMTradeAdvisor(self.cfg)
            logger.info("News layer initialized: %d sources", self._news_poller.source_count)
        except Exception as e:
            logger.warning("News layer setup failed: %s", e)

    # ── Regime ────────────────────────────────────────────────────────

    def get_effective_regime(self) -> Optional[str]:
        """Return the effective regime, with news override taking priority."""
        if self._news_regime_override:
            return self._news_regime_override
        return self._current_regime

    def _update_regime(self, data_15m: pd.DataFrame, data_1h: Optional[pd.DataFrame] = None):
        """Classify current market regime from latest OHLC data."""
        if data_15m.empty or len(data_15m) < 50:
            return

        regime_series = self._regime_detector.classify(
            data_15m, data_1h if data_1h is not None and not data_1h.empty else None,
        )
        self._current_regime = regime_series.iloc[-1]

        _atr = compute_atr(data_15m, period=14)
        if not _atr.empty:
            self._current_atr = float(_atr.iloc[-1])

        self._last_regime_update = datetime.now(timezone.utc)
        logger.info("Regime updated: %s (ATR: %.2f)", self._current_regime, self._current_atr)

    # ── Data Loading ──────────────────────────────────────────────────

    def _load_recent_data(
        self,
        tf: str = "15m",
        bars: int = 300,
        source_override: Optional[str] = None,
    ) -> tuple[pd.DataFrame, str]:
        """Load recent OHLC bars using configured market data source."""
        symbol = self.cfg.get("symbol", "XAUUSD")
        base_path = Path(self.cfg.get("data", {}).get("base_path", "data/market_cache"))
        data_source = str(source_override or self.cfg.get("data", {}).get("source", "auto")).lower()
        stale_limit = 60 if tf == "1h" else 30

        data = ensure_live_data(
            symbol=symbol,
            timeframe=tf,
            base_path=base_path,
            min_bars=bars,
            max_stale_minutes=stale_limit,
            source=data_source,
            broker=self.broker,
        )
        source_actual = str(data.attrs.get("source_actual", "unknown"))
        if not data.empty:
            data = data.sort_index().tail(bars)
        self._last_data_source = source_actual
        return data, source_actual

    def _bootstrap_market_data(self) -> bool:
        """Fetch initial bar history at startup. Returns False on failure."""
        symbol = self.cfg.get("symbol", "XAUUSD")
        timeframes = self.cfg.get("data", {}).get("timeframes", ["15m", "1h"])
        data_source = str(self.cfg.get("data", {}).get("source", "auto")).lower()

        logger.info("=== MARKET DATA BOOTSTRAP ===")
        logger.info("symbol=%s timeframes=%s source=%s", symbol, timeframes, data_source)

        all_ok = True
        coherent_source: Optional[str] = None
        tf_sources: Dict[str, str] = {}
        for tf in timeframes:
            source_override = coherent_source if data_source == "auto" and coherent_source else None
            data, source_actual = self._load_recent_data(tf, bars=300, source_override=source_override)
            tf_sources[tf] = source_actual
            bar_count = len(data)
            last_ts = str(data.index[-1]) if not data.empty else "None"
            first_ts = str(data.index[0]) if not data.empty else "None"

            logger.info(
                "warmup_check symbol=%s timeframe=%s required=%d received=%d source_actual=%s "
                "first_ts=%s last_ts=%s",
                symbol, tf, MIN_BARS_FOR_SIGNAL, bar_count, source_actual, first_ts, last_ts,
            )

            if bar_count < MIN_BARS_FOR_SIGNAL:
                logger.error(
                    "bootstrap_tf_fail symbol=%s timeframe=%s source_actual=%s bars=%d need=%d "
                    "message='Signal engine will not fire.'",
                    symbol, tf, source_actual, bar_count, MIN_BARS_FOR_SIGNAL,
                )
                logger.error(
                    "BOOTSTRAP FAILED: %s %s — got %d bars, need %d. "
                    "Signal engine will not fire.",
                    symbol, tf, bar_count, MIN_BARS_FOR_SIGNAL,
                )
                all_ok = False
            else:
                if data_source == "auto" and coherent_source is None and source_actual in {"ctrader", "dukascopy"}:
                    coherent_source = source_actual
                sample = data.iloc[-1]
                logger.info(
                    "warmup_sample symbol=%s tf=%s O=%.2f H=%.2f L=%.2f C=%.2f",
                    symbol, tf, sample["open"], sample["high"],
                    sample["low"], sample["close"],
                )
                logger.info(
                    "bootstrap_tf_success symbol=%s timeframe=%s source_actual=%s bars=%d first_ts=%s last_ts=%s",
                    symbol, tf, source_actual, bar_count, first_ts, last_ts,
                )

        unique_sources = {s for s in tf_sources.values() if s and s != "unknown"}
        if len(unique_sources) > 1:
            logger.warning(
                "bootstrap_source_coherence_warning symbol=%s sources=%s tf_sources=%s",
                symbol, sorted(unique_sources), tf_sources,
            )
        elif unique_sources:
            only = next(iter(unique_sources))
            logger.info("bootstrap_source_coherence_ok symbol=%s source=%s tf_sources=%s", symbol, only, tf_sources)

        logger.info("=== BOOTSTRAP %s ===", "OK" if all_ok else "FAILED")
        return all_ok

    # ── Execution Guardrails ──────────────────────────────────────────

    def _check_spread_guard(self) -> Optional[Dict[str, Any]]:
        """Return a block detail dict if spread guard fails; None if OK.

        Keys when blocked: ``code`` (internal), ``detail`` (human), ``observed`` (pips),
        ``threshold`` (pips). ``observed``/``threshold`` may be None when unknown.
        """
        if self.dry_run:
            return None
        price_info = self.broker.get_current_price()
        if price_info is None:
            return {
                "code": "price_unavailable",
                "detail": "price_unavailable",
                "observed": None,
                "threshold": None,
            }
        spread = float(price_info.get("spread", 0) or 0.0)
        threshold = float(self._max_spread_pips)
        if spread > threshold:
            return {
                "code": "spread_block",
                "detail": f"spread_too_wide ({spread:.2f} > {threshold})",
                "observed": spread,
                "threshold": threshold,
            }
        return None

    def _try_current_spread_pips(self) -> Optional[float]:
        """Best-effort live spread in pips for telemetry; None in dry-run or if unavailable."""
        if self.dry_run or not getattr(self.broker, "is_connected", False):
            return None
        try:
            price_info = self.broker.get_current_price()
        except Exception:
            return None
        if not price_info:
            return None
        raw = price_info.get("spread")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _check_position_limit(self) -> bool:
        """Return True if we can open another position."""
        return len(self.position_monitor.open_positions) < self._max_open_positions

    def _check_daily_loss_limit(self) -> bool:
        """Return True if daily loss limit is not breached."""
        return self._daily_pnl_r > -self._max_daily_loss_r

    def _reset_daily_tracking(self, now: datetime):
        """Reset daily counters on new trading day."""
        today = now.strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_date = today
            self._daily_pnl_r = 0.0
            self._daily_trade_count = 0
            logger.info("New trading day: %s", today)

    def _daily_account_state_path(self) -> Path:
        base = Path(self.cfg.get("data", {}).get("base_path", "data/market_cache"))
        state_dir = base / "runtime_state"
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir / "daily_account_baseline.json"

    def _load_daily_account_state(self) -> None:
        path = self._daily_account_state_path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            date_val = raw.get("date")
            equity_val = raw.get("equity")
            if isinstance(date_val, str):
                self._daily_account_baseline_date = date_val
            if equity_val is not None:
                self._daily_account_baseline_equity = float(equity_val)
            set_at_val = raw.get("set_at")
            if isinstance(set_at_val, str) and set_at_val.strip():
                self._daily_account_baseline_set_at = set_at_val.strip()
            elif self._daily_account_baseline_date:
                self._daily_account_baseline_set_at = f"{self._daily_account_baseline_date} 00:00 UTC"
        except Exception as e:
            logger.warning("Failed to load daily account baseline: %s", e)

    def _save_daily_account_state(self) -> None:
        if self._daily_account_baseline_date is None or self._daily_account_baseline_equity is None:
            return
        payload = {
            "date": self._daily_account_baseline_date,
            "equity": float(self._daily_account_baseline_equity),
            "set_at": self._daily_account_baseline_set_at,
        }
        try:
            path = self._daily_account_state_path()
            path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to save daily account baseline: %s", e)

    def _update_daily_account_baseline(self, now: datetime, equity: Optional[float]) -> Optional[float]:
        if equity is None:
            return None
        today = now.strftime("%Y-%m-%d")
        if self._daily_account_baseline_date != today or self._daily_account_baseline_equity is None:
            self._daily_account_baseline_date = today
            self._daily_account_baseline_equity = float(equity)
            self._daily_account_baseline_set_at = now.strftime("%Y-%m-%d %H:%M UTC")
            self._save_daily_account_state()
            logger.info(
                "Daily account baseline set: date=%s equity=%.2f",
                self._daily_account_baseline_date,
                self._daily_account_baseline_equity,
            )
        return float(equity) - float(self._daily_account_baseline_equity)

    # ── Position Sync ─────────────────────────────────────────────────

    def _sync_positions_from_broker(self):
        """Sync position monitor with actual broker positions."""
        if self.dry_run or not self.broker.is_connected:
            return

        broker_trades = self.broker.get_open_trades()
        broker_ids = {t.trade_id for t in broker_trades}
        monitor_ids = {p.trade_id for p in self.position_monitor.all_positions}

        # Add new positions from broker
        for bt in broker_trades:
            if bt.trade_id not in monitor_ids:
                pos = Position(
                    trade_id=bt.trade_id,
                    instrument=bt.instrument,
                    direction=bt.direction,
                    entry_price=bt.entry_price,
                    units=bt.units,
                    current_price=bt.current_price,
                    unrealized_pnl=bt.unrealized_pnl,
                    sl=bt.sl or 0.0,
                    tp=bt.tp or 0.0,
                    open_time=bt.open_time or datetime.now(timezone.utc),
                )
                self.position_monitor.add_position(pos)
                logger.info("Synced position from broker: %s %s", bt.trade_id, bt.direction)

        # Remove closed positions
        for mid in monitor_ids - broker_ids:
            removed = self.position_monitor.remove_position(mid)
            self.order_manager.unregister_trade(mid, reason="closed_by_broker")
            if removed is not None:
                ex = float(removed.current_price or removed.entry_price)
                try:
                    pr = calculate_rr(removed.entry_price, ex, removed.sl, removed.direction.value)
                except Exception:
                    pr = 0.0
                self._emit_trade_closed(
                    trade_id=mid,
                    exit_price=ex,
                    pnl_r=float(pr),
                    outcome="closed_external",
                    exit_tag="broker_sync",
                    pnl_abs=float(removed.unrealized_pnl),
                    direction=removed.direction.value,
                )

        # Update prices
        for bt in broker_trades:
            self.position_monitor.update_price(bt.trade_id, bt.current_price)
            self.order_manager.update_price(bt.trade_id, bt.current_price)

    # ── Signal Evaluation ─────────────────────────────────────────────

    def _new_trace_id(self) -> str:
        return f"trace_qb_{uuid4().hex[:12]}"

    def _runner_pre_signal_decision_context(
        self,
        *,
        eval_stage: str,
        regime: Optional[str],
        session: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {
            "decision_context_version": 1,
            "strategy": "sqe_xauusd",
            "eval_stage": eval_stage,
            "session": session,
            "regime": regime or "none",
            "system_mode": getattr(self, "_system_mode", SYSTEM_MODE_PRODUCTION),
            "bypassed_by_mode": getattr(self, "_bypassed_by_mode", []),
        }
        ctx.update(extra)
        return ctx

    def _emit_signal_evaluated(
        self,
        *,
        trace_id: str,
        direction: str,
        confidence: float,
        regime: Optional[str],
        setup: bool = True,
        eval_stage: Optional[str] = None,
        decision_context: Optional[Dict[str, Any]] = None,
        decision_cycle_id: Optional[str] = None,
    ) -> None:
        if eval_stage == "same_bar_already_processed":
            self._hourly_signal_eval_same_bar += 1
        else:
            self._hourly_signal_eval_new_bar += 1

        self._telemetry_eval_stage = eval_stage or self._telemetry_eval_stage
        if decision_context:
            lb = decision_context.get("latest_bar_ts")
            if lb is not None:
                self._telemetry_latest_bar_ts = str(lb)
            lp = decision_context.get("last_processed_bar_ts")
            if lp is not None:
                self._telemetry_last_processed_bar_ts = str(lp)
            sa = decision_context.get("source_actual")
            if sa is not None:
                self._telemetry_source_actual = str(sa)

        poll_ts = datetime.now(timezone.utc)
        bar_ts_key: Optional[str] = None
        if isinstance(decision_context, dict):
            lb = decision_context.get("latest_bar_ts")
            if lb is not None:
                bar_ts_key = str(lb)
        prev_stage = (
            self._eval_stage_by_bar_ts.get(bar_ts_key) if bar_ts_key else None
        )
        skip_for_bar = 0
        if eval_stage == "same_bar_already_processed" and bar_ts_key:
            skip_for_bar = self._same_bar_skip_by_bar_ts.get(bar_ts_key, 0) + 1
            self._same_bar_skip_by_bar_ts[bar_ts_key] = skip_for_bar
        new_bar_detected = bool(
            eval_stage and eval_stage not in ("same_bar_already_processed", "bars_missing")
        )
        if bar_ts_key and eval_stage:
            self._eval_stage_by_bar_ts[bar_ts_key] = eval_stage

        if not self._quantlog:
            return
        desk_extra = build_desk_grade_payload(
            eval_stage=eval_stage,
            decision_context=decision_context,
            setup=setup,
            direction=direction,
            confidence=confidence,
            same_bar_skip_count_for_bar=skip_for_bar,
            previous_eval_stage_on_bar=prev_stage,
            poll_ts=poll_ts,
            bar_ts_str=bar_ts_key,
            new_bar_detected=new_bar_detected,
        )
        dcid_eff = (decision_cycle_id or "").strip()
        if not dcid_eff:
            dcid_eff = f"dc_live_{uuid4().hex[:12]}"
        sess_hint = ""
        if isinstance(decision_context, dict):
            s0 = decision_context.get("session")
            if s0 is not None:
                sess_hint = str(s0)
        payload = build_signal_evaluated_payload(
            decision_cycle_id=dcid_eff,
            session=sess_hint,
            regime=regime,
            signal_type="sqe_entry",
            signal_direction=direction,
            confidence=confidence,
            system_mode=getattr(self, "_system_mode", SYSTEM_MODE_PRODUCTION),
            bypassed_by_mode=list(getattr(self, "_bypassed_by_mode", []) or []),
            setup_type="sqe",
            setup=setup,
            eval_stage=eval_stage,
            decision_context=decision_context,
            desk_extra=desk_extra,
        )
        assert_signal_evaluated_payload_complete(payload)
        self._quantlog.emit(
            event_type="signal_evaluated",
            trace_id=trace_id,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            payload=payload,
            decision_cycle_id=dcid_eff,
        )

    def _emit_guard_decision(
        self,
        *,
        trace_id: str,
        decision: str,
        reason: str,
        guard_name: str,
        decision_cycle_id: Optional[str] = None,
        threshold: Optional[float] = None,
        observed_value: Optional[float] = None,
        session: Optional[str] = None,
        regime: Optional[str] = None,
    ) -> None:
        if not self._quantlog:
            return
        from src.quantbuild.execution.quantlog_no_action import canonical_no_action_reason

        eff_reason = (
            canonical_no_action_reason(reason)
            if (decision or "").upper() == "BLOCK"
            else reason
        )
        payload: Dict[str, Any] = {
            "guard_name": guard_name,
            "decision": decision,
            "reason": eff_reason,
        }
        if threshold is not None:
            payload["threshold"] = threshold
        if observed_value is not None:
            payload["observed_value"] = observed_value
        if session is not None:
            payload["session"] = session
        if regime is not None:
            payload["regime"] = regime or "none"
        self._quantlog.emit(
            event_type="risk_guard_decision",
            trace_id=trace_id,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            payload=payload,
            decision_cycle_id=decision_cycle_id,
        )

    def _emit_trade_action(
        self,
        *,
        trace_id: str,
        decision: str,
        reason: str,
        side: Optional[str] = None,
        session: Optional[str] = None,
        regime: Optional[str] = None,
        decision_context: Optional[Dict[str, Any]] = None,
        decision_cycle_id: Optional[str] = None,
        trade_id: Optional[str] = None,
    ) -> None:
        from src.quantbuild.execution.quantlog_no_action import canonical_no_action_reason

        eff_reason = canonical_no_action_reason(reason) if decision == "NO_ACTION" else reason
        if decision == "NO_ACTION":
            self._hourly_no_action_counts[eff_reason] += 1
        elif decision == "ENTER":
            self._hourly_enter_count += 1
        if not self._quantlog:
            return
        payload: Dict[str, Any] = {
            "decision": decision,
            "reason": eff_reason,
            "system_mode": getattr(self, "_system_mode", SYSTEM_MODE_PRODUCTION),
            "bypassed_by_mode": getattr(self, "_bypassed_by_mode", []),
        }
        if side:
            payload["side"] = side
        if session is not None:
            payload["session"] = session
        if regime is not None:
            payload["regime"] = regime
        if decision_context is not None:
            payload["decision_context"] = decision_context
        if trade_id:
            payload["trade_id"] = trade_id
        self._quantlog.emit(
            event_type="trade_action",
            trace_id=trace_id,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            payload=payload,
            decision_cycle_id=decision_cycle_id,
        )

    def _bar_lag_minutes(self, now: datetime) -> Optional[float]:
        """Wall-clock UTC lag vs last 15m bar index (telemetry from last signal_evaluated)."""
        raw = self._telemetry_latest_bar_ts
        if not raw:
            return None
        try:
            ts = pd.Timestamp(raw)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            now_ts = pd.Timestamp(now.astimezone(timezone.utc))
            return float((now_ts - ts).total_seconds() / 60.0)
        except Exception:
            return None

    def _emit_market_data_stale_warning(
        self,
        *,
        trace_id: str,
        bar_lag_minutes: float,
        latest_bar_ts_utc: str,
        session: str,
        threshold_minutes: float,
        source_actual: Optional[str],
    ) -> None:
        if not self._quantlog:
            return
        payload: Dict[str, Any] = {
            "symbol": str(self.cfg.get("symbol", "XAUUSD")),
            "bar_lag_minutes": round(float(bar_lag_minutes), 2),
            "latest_bar_ts_utc": latest_bar_ts_utc,
            "session": session,
            "threshold_minutes": float(threshold_minutes),
        }
        if source_actual:
            payload["source_actual"] = source_actual
        self._quantlog.emit(
            event_type="market_data_stale_warning",
            trace_id=trace_id,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            payload=payload,
            severity="warn",
        )

    def _maybe_emit_market_data_stale_warning(self, now: datetime, session: str) -> None:
        """Once per stale episode while in ENTRY_SESSIONS and bar lag exceeds threshold."""
        if session not in ENTRY_SESSIONS:
            return
        lag = self._bar_lag_minutes(now)
        if lag is None:
            return
        if lag <= STALE_BAR_LAG_WARN_MINUTES:
            self._stale_bar_warn_latched = False
            return
        if self._stale_bar_warn_latched:
            return
        self._stale_bar_warn_latched = True
        latest = self._telemetry_latest_bar_ts or ""
        src = self._telemetry_source_actual
        tid = self._new_trace_id()
        if not self._quantlog:
            logger.warning(
                "market_data_stale: bar_lag_minutes=%.2f latest_bar_ts=%s session=%s "
                "(QuantLog disabled — no market_data_stale_warning event)",
                lag,
                latest,
                session,
            )
            return
        self._emit_market_data_stale_warning(
            trace_id=tid,
            bar_lag_minutes=lag,
            latest_bar_ts_utc=latest,
            session=session,
            threshold_minutes=STALE_BAR_LAG_WARN_MINUTES,
            source_actual=src,
        )
        logger.warning(
            "Emitted market_data_stale_warning: bar_lag_minutes=%.2f latest_bar_ts=%s session=%s",
            lag,
            latest,
            session,
        )

    def _emit_signal_detected(
        self,
        *,
        trace_id: str,
        signal_id: str,
        direction: str,
        strength: float,
        bar_timestamp: str,
        regime: Optional[str],
        session: str,
        modules_hint: Optional[Dict[str, Any]] = None,
        decision_cycle_id: Optional[str] = None,
        entry_type: str = "sqe_entry",
    ) -> None:
        if not self._quantlog:
            return
        payload: Dict[str, Any] = {
            "signal_id": signal_id,
            "type": entry_type,
            "direction": direction,
            "strength": strength,
            "bar_timestamp": bar_timestamp,
            "session": session,
            "regime": regime or "none",
            "system_mode": getattr(self, "_system_mode", SYSTEM_MODE_PRODUCTION),
            "bypassed_by_mode": getattr(self, "_bypassed_by_mode", []),
        }
        if modules_hint:
            payload["modules"] = modules_hint
        self._quantlog.emit(
            event_type="signal_detected",
            trace_id=trace_id,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            payload=payload,
            decision_cycle_id=decision_cycle_id,
        )

    def _emit_pipeline_gate_signal_detected(
        self,
        *,
        trace_id: str,
        decision_cycle_id: str,
        current_session: str,
        regime: Optional[str],
        bar_timestamp: str,
        eval_stage: str,
    ) -> None:
        """Emit a synthetic ``signal_detected`` so every ``signal_evaluated`` has a preceding detect (P0 funnel)."""
        if not self._quantlog:
            return
        signal_id = f"sig_cycle_{uuid4().hex[:12]}"
        self._emit_signal_detected(
            trace_id=trace_id,
            signal_id=signal_id,
            direction="LONG",
            strength=0.0,
            bar_timestamp=bar_timestamp,
            regime=regime,
            session=current_session,
            modules_hint={"synthetic_cycle_anchor": True, "eval_stage": eval_stage},
            decision_cycle_id=decision_cycle_id,
            entry_type="sqe_pipeline_scan",
        )

    def _emit_signal_filtered(
        self,
        *,
        trace_id: str,
        signal_id: Optional[str],
        raw_reason: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._quantlog:
            return
        from src.quantbuild.execution.quantlog_no_action import canonical_no_action_reason

        payload: Dict[str, Any] = {
            "filter_reason": canonical_no_action_reason(raw_reason),
            "raw_reason": raw_reason,
        }
        if signal_id:
            payload["signal_id"] = signal_id
        if extra:
            payload["detail"] = extra
        self._quantlog.emit(
            event_type="signal_filtered",
            trace_id=trace_id,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            payload=payload,
        )

    @staticmethod
    def _direction_label_for_quantlog(direction: Any) -> str:
        if hasattr(direction, "value"):
            return str(getattr(direction, "value"))
        s = str(direction).upper()
        if s in ("LONG", "SHORT"):
            return s
        if "BUY" in s or s == "LONG":
            return "LONG"
        return "SHORT"

    def _register_open_trade_quantlog(
        self,
        trade_id: str,
        *,
        trace_id: str,
        decision_cycle_id: Optional[str],
        session: str,
        regime: Optional[str],
        direction: str,
        entry_price: float,
        signal_id: Optional[str] = None,
    ) -> None:
        self._open_trade_quantlog[trade_id] = {
            "trace_id": trace_id,
            "decision_cycle_id": decision_cycle_id,
            "session": session,
            "regime": regime or "none",
            "direction": self._direction_label_for_quantlog(direction),
            "entry_price": float(entry_price),
            "signal_id": signal_id,
        }

    def _emit_trade_closed(
        self,
        *,
        trade_id: str,
        exit_price: float,
        pnl_r: float,
        outcome: str,
        exit_tag: str,
        trace_id: Optional[str] = None,
        decision_cycle_id: Optional[str] = None,
        session: Optional[str] = None,
        regime: Optional[str] = None,
        direction: Optional[str] = None,
        pnl_abs: Optional[float] = None,
        mae_r: float = 0.0,
        mfe_r: float = 0.0,
    ) -> None:
        """Emit ``trade_closed`` for lifecycle closure (P0-D). Uses ENTER registration when available."""
        if not self._quantlog:
            return
        meta = self._open_trade_quantlog.pop(trade_id, None)
        eff_trace = trace_id or (meta or {}).get("trace_id") or self._new_trace_id()
        eff_dcid = decision_cycle_id if decision_cycle_id else (meta or {}).get("decision_cycle_id")
        eff_session = session or (meta or {}).get("session") or "unknown"
        eff_regime = regime or (meta or {}).get("regime") or "none"
        d_lab = direction or (meta or {}).get("direction") or "LONG"
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ref = str(trade_id)
        pl_abs = float(0.0 if pnl_abs is None else pnl_abs)
        payload: Dict[str, Any] = {
            "trade_id": ref,
            "order_ref": ref,
            "direction": self._direction_label_for_quantlog(d_lab),
            "exit_price": float(exit_price),
            "pnl_abs": pl_abs,
            "pnl_r": float(pnl_r),
            "mae_r": float(mae_r),
            "mfe_r": float(mfe_r),
            "outcome": outcome,
            "exit": exit_tag,
            "session": eff_session,
            "regime": eff_regime,
        }
        if isinstance(eff_dcid, str) and eff_dcid.strip():
            payload["decision_cycle_id"] = eff_dcid.strip()
        self._quantlog.emit(
            event_type="trade_closed",
            trace_id=eff_trace,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            order_ref=ref,
            decision_cycle_id=eff_dcid if isinstance(eff_dcid, str) and eff_dcid.strip() else None,
            timestamp_utc=ts,
            payload=payload,
        )

    def _emit_trade_executed(
        self,
        *,
        trace_id: str,
        signal_id: Optional[str],
        direction: str,
        trade_id: str,
        regime: Optional[str],
        session: str,
        decision_cycle_id: Optional[str] = None,
    ) -> None:
        if not self._quantlog:
            return
        payload: Dict[str, Any] = {
            "direction": direction,
            "trade_id": trade_id,
            "session": session,
            "regime": regime or "none",
        }
        if signal_id:
            payload["signal_id"] = signal_id
        if isinstance(decision_cycle_id, str) and decision_cycle_id.strip():
            payload["decision_cycle_id"] = decision_cycle_id.strip()
        self._quantlog.emit(
            event_type="trade_executed",
            trace_id=trace_id,
            account_id=self._account_id,
            strategy_id="sqe_live_runner",
            symbol=self.cfg.get("symbol", "XAUUSD"),
            order_ref=str(trade_id),
            decision_cycle_id=decision_cycle_id if isinstance(decision_cycle_id, str) and decision_cycle_id.strip() else None,
            payload=payload,
        )

    def _log_decision_cycle(
        self,
        now: datetime,
        action: str,
        reason: str,
        regime: Optional[str],
        killzone: str,
        source_actual: str = "unknown",
        bias: str = "none",
        bars_ok: Optional[bool] = None,
        long_signal: Optional[bool] = None,
        short_signal: Optional[bool] = None,
        position_ok: Optional[bool] = None,
        daily_loss_ok: Optional[bool] = None,
    ) -> None:
        self._decision_cycle_n += 1
        logger.info(
            "decision_cycle n=%d symbol=%s ts=%s regime=%s killzone=%s source=%s "
            "bars_ok=%s long_signal=%s short_signal=%s position_ok=%s daily_loss_ok=%s "
            "bias=%s action=%s reason=%s",
            self._decision_cycle_n,
            self.cfg.get("symbol", "XAUUSD"),
            now.isoformat(),
            regime or "none",
            killzone,
            source_actual,
            bars_ok if bars_ok is not None else "na",
            long_signal if long_signal is not None else "na",
            short_signal if short_signal is not None else "na",
            position_ok if position_ok is not None else "na",
            daily_loss_ok if daily_loss_ok is not None else "na",
            bias,
            action,
            reason,
        )

    def _compute_sqe_signal_state(
        self, data_15m: pd.DataFrame
    ) -> tuple[Any, int, Dict[str, Any], List[str], bool, bool]:
        """SQE precompute + last-bar LONG/SHORT flags (shared by standard and research paths)."""
        sqe_cfg = get_sqe_default_config()
        strategy_cfg = self.cfg.get("strategy", {}) or {}
        if strategy_cfg:
            from src.quantbuild.backtest.engine import _deep_merge

            _deep_merge(sqe_cfg, strategy_cfg)
        precomputed_df = _compute_modules_once(data_15m, sqe_cfg)
        long_entries = run_sqe_conditions(data_15m, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
        short_entries = run_sqe_conditions(data_15m, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)
        last_idx = len(data_15m) - 1
        signals_to_check: List[str] = []
        if long_entries.iloc[last_idx]:
            signals_to_check.append("LONG")
        if short_entries.iloc[last_idx]:
            signals_to_check.append("SHORT")
        long_signal = bool(long_entries.iloc[last_idx])
        short_signal = bool(short_entries.iloc[last_idx])
        return precomputed_df, last_idx, sqe_cfg, signals_to_check, long_signal, short_signal

    def _check_signals_research_raw_first(
        self,
        now: datetime,
        regime: Optional[str],
        regime_profiles: Dict[str, Any],
        current_session: str,
        position_ok: bool,
        daily_loss_ok: bool,
        cycle_trace_id: str,
        cycle_decision_id: str,
    ) -> None:
        """Compute SQE before regime/session gates; log signal_detected then signal_filtered or execute."""

        if self._filter_position_limit and not position_ok:
            logger.debug("Position limit reached (%d)", self._max_open_positions)
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="position_limit_block",
                regime=regime,
                session=current_session,
                max_open_positions=self._max_open_positions,
            )
            wall_ts = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=wall_ts,
                eval_stage="position_limit_block",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="position_limit_block",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="position_limit_block",
                regime=regime,
                killzone=current_session,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="position_limit_block",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        if self._filter_daily_loss and not daily_loss_ok:
            logger.warning("Daily loss limit reached (%.2fR)", self._daily_pnl_r)
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="daily_loss_block",
                regime=regime,
                session=current_session,
                daily_pnl_r=float(self._daily_pnl_r),
            )
            wall_ts = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=wall_ts,
                eval_stage="daily_loss_block",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="daily_loss_block",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="daily_loss_block",
                regime=regime,
                killzone=current_session,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="daily_loss_block",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        data_15m, source_actual = self._load_recent_data("15m", bars=300)
        if data_15m.empty or len(data_15m) < MIN_BARS_FOR_SIGNAL:
            symbol = self.cfg.get("symbol", "XAUUSD")
            last_ts = str(data_15m.index[-1]) if not data_15m.empty else "None"
            logger.warning(
                "signal_warmup_check symbol=%s timeframe=15m required=%d "
                "received=%d last_ts=%s source=%s_cache",
                symbol,
                MIN_BARS_FOR_SIGNAL,
                len(data_15m),
                last_ts,
                source_actual,
            )
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="bars_missing",
                regime=regime,
                session=current_session,
                source_actual=source_actual,
                bar_count=len(data_15m),
                min_bars=MIN_BARS_FOR_SIGNAL,
            )
            bar_anchor = (
                last_ts
                if not data_15m.empty
                else now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=bar_anchor,
                eval_stage="bars_missing",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="bars_missing",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="bars_missing",
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bars_ok=False,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="bars_missing",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        latest_ts = data_15m.index[-1]
        if self._filter_cooldown and self._last_bar_ts is not None and latest_ts <= self._last_bar_ts:
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="same_bar_already_processed",
                regime=regime,
                session=current_session,
                latest_bar_ts=str(latest_ts),
                last_processed_bar_ts=str(self._last_bar_ts),
            )
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=str(latest_ts),
                eval_stage="same_bar_already_processed",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="same_bar_already_processed",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="same_bar_already_processed",
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bars_ok=True,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="same_bar_already_processed",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return
        if self._filter_cooldown:
            self._last_bar_ts = latest_ts

        precomputed_df, last_idx, sqe_cfg, signals_to_check, long_signal, short_signal = (
            self._compute_sqe_signal_state(data_15m)
        )

        if not signals_to_check:
            logger.debug("No entry signals at %s", now.strftime("%H:%M"))
            long_ctx = sqe_decision_context_at_bar(precomputed_df, "LONG", last_idx, sqe_cfg)
            short_ctx = sqe_decision_context_at_bar(precomputed_df, "SHORT", last_idx, sqe_cfg)
            long_ctx["session"] = current_session
            short_ctx["session"] = current_session
            if regime is not None:
                long_ctx["regime"] = regime
                short_ctx["regime"] = regime
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="no_entry_signal",
                regime=regime,
                session=current_session,
                long=long_ctx,
                short=short_ctx,
                latest_bar_ts=str(data_15m.index[-1]),
                last_processed_bar_ts=str(self._last_bar_ts)
                if self._last_bar_ts is not None
                else None,
                source_actual=source_actual,
            )
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=str(data_15m.index[-1]),
                eval_stage="no_entry_signal",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="no_entry_signal",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="no_entry_signal",
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bars_ok=True,
                long_signal=long_signal,
                short_signal=short_signal,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="no_entry_signal",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        pending: List[tuple[str, str, str, Dict[str, Any], str]] = []
        for direction in signals_to_check:
            trace_id = self._new_trace_id()
            signal_id = str(uuid4())
            d_cycle = cycle_decision_id
            sqe_ctx = sqe_decision_context_at_bar(precomputed_df, direction, last_idx, sqe_cfg)
            sqe_ctx["session"] = current_session
            if regime is not None:
                sqe_ctx["regime"] = regime
            mod_keys = ("mss_confirmed", "sweep_detected", "fvg_in_zone", "displacement_trigger")
            modules_hint = {k: sqe_ctx[k] for k in mod_keys if k in sqe_ctx}
            self._emit_signal_detected(
                trace_id=trace_id,
                signal_id=signal_id,
                direction=direction,
                strength=1.0,
                bar_timestamp=str(data_15m.index[last_idx]),
                regime=regime,
                session=current_session,
                modules_hint=modules_hint or None,
                decision_cycle_id=d_cycle,
            )
            pending.append((direction, trace_id, signal_id, sqe_ctx, d_cycle))

        rp = regime_profiles.get(regime, {}) if regime else {}
        if self._filter_regime and regime and rp.get("skip", False):
            for _d, tid, sid, _sqe, _dc in pending:
                self._emit_signal_filtered(
                    trace_id=tid, signal_id=sid, raw_reason="regime_block"
                )
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="regime_block", regime=regime, session=current_session
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=pending[0][4],
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="regime_block",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="regime_block",
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                long_signal=long_signal,
                short_signal=short_signal,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=pending[0][4],
                decision="NO_ACTION",
                reason="regime_block",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        if self._filter_session and regime:
            allowed_sessions = rp.get("allowed_sessions")
            if allowed_sessions and current_session not in allowed_sessions:
                for _d, tid, sid, _sqe, _dc in pending:
                    self._emit_signal_filtered(
                        trace_id=tid, signal_id=sid, raw_reason="outside_killzone"
                    )
                pre_ctx = self._runner_pre_signal_decision_context(
                    eval_stage="outside_killzone",
                    regime=regime,
                    session=current_session,
                    allowed_sessions=list(allowed_sessions),
                )
                self._emit_signal_evaluated(
                    trace_id=cycle_trace_id,
                    decision_cycle_id=pending[0][4],
                    direction="NONE",
                    confidence=0.0,
                    regime=regime,
                    setup=False,
                    eval_stage="outside_killzone",
                    decision_context=pre_ctx,
                )
                self._log_decision_cycle(
                    now=now,
                    action="no_trade",
                    reason="outside_killzone",
                    regime=regime,
                    killzone=current_session,
                    source_actual=source_actual,
                    long_signal=long_signal,
                    short_signal=short_signal,
                    position_ok=position_ok,
                    daily_loss_ok=daily_loss_ok,
                )
                self._emit_trade_action(
                    trace_id=cycle_trace_id,
                    decision_cycle_id=pending[0][4],
                    decision="NO_ACTION",
                    reason="outside_killzone",
                    session=current_session,
                    regime=regime,
                    decision_context=pre_ctx,
                )
                return
            min_hour = rp.get("min_hour_utc")
            if min_hour is not None and now.hour < min_hour:
                for _d, tid, sid, _sqe, _dc in pending:
                    self._emit_signal_filtered(
                        trace_id=tid, signal_id=sid, raw_reason="time_filter_block"
                    )
                pre_ctx = self._runner_pre_signal_decision_context(
                    eval_stage="time_filter_block",
                    regime=regime,
                    session=current_session,
                    min_hour_utc=min_hour,
                    hour_utc=now.hour,
                )
                self._emit_signal_evaluated(
                    trace_id=cycle_trace_id,
                    decision_cycle_id=pending[0][4],
                    direction="NONE",
                    confidence=0.0,
                    regime=regime,
                    setup=False,
                    eval_stage="time_filter_block",
                    decision_context=pre_ctx,
                )
                self._log_decision_cycle(
                    now=now,
                    action="no_trade",
                    reason="time_filter_block",
                    regime=regime,
                    killzone=current_session,
                    source_actual=source_actual,
                    long_signal=long_signal,
                    short_signal=short_signal,
                    position_ok=position_ok,
                    daily_loss_ok=daily_loss_ok,
                )
                self._emit_trade_action(
                    trace_id=cycle_trace_id,
                    decision_cycle_id=pending[0][4],
                    decision="NO_ACTION",
                    reason="time_filter_block",
                    session=current_session,
                    regime=regime,
                    decision_context=pre_ctx,
                )
                return

        for direction, trace_id, signal_id, sqe_ctx, d_cycle in pending:
            bar_iso = str(data_15m.index[last_idx])
            emit_ctx = dict(sqe_ctx)
            emit_ctx["latest_bar_ts"] = bar_iso
            try:
                emit_ctx["price_at_signal"] = float(data_15m["close"].iloc[last_idx])
            except (KeyError, TypeError, ValueError):
                pass
            sp_live = self._try_current_spread_pips()
            if sp_live is not None:
                emit_ctx["spread_pips"] = sp_live
            self._emit_signal_evaluated(
                trace_id=trace_id,
                direction=direction,
                confidence=1.0,
                regime=regime,
                decision_context=emit_ctx,
                decision_cycle_id=d_cycle,
            )
            action, reason = self._evaluate_and_execute(
                direction,
                data_15m,
                now,
                regime,
                trace_id,
                current_session,
                strategy_decision_context=sqe_ctx,
                signal_id=signal_id,
                decision_cycle_id=d_cycle,
            )
            self._log_decision_cycle(
                now=now,
                action=action,
                reason=reason,
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bias=direction.lower(),
                bars_ok=True,
                long_signal=long_signal,
                short_signal=short_signal,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )

    def _check_signals(self, now: datetime):
        """Evaluate SQE entry signals and submit orders when criteria are met."""
        regime = self.get_effective_regime()
        regime_profiles = self.cfg.get("regime_profiles", {})
        session_mode = self.cfg.get("backtest", {}).get("session_mode", "killzone")
        current_session = session_from_timestamp(now, mode=session_mode)
        position_ok = self._check_position_limit()
        daily_loss_ok = self._check_daily_loss_limit()
        # One trace for pre-signal exits in this cycle (PLATFORM_ROADMAP P3 / QUANTBUILD_ROADMAP).
        cycle_trace_id = self._new_trace_id()
        cycle_decision_id = str(uuid4())

        if self._research_raw_first:
            self._check_signals_research_raw_first(
                now,
                regime,
                regime_profiles,
                current_session,
                position_ok,
                daily_loss_ok,
                cycle_trace_id,
                cycle_decision_id,
            )
            return

        # Regime skip
        if regime:
            rp = regime_profiles.get(regime, {})
            if self._filter_regime and rp.get("skip", False):
                logger.debug("Regime %s -> skip", regime)
                pre_ctx = self._runner_pre_signal_decision_context(
                    eval_stage="regime_block", regime=regime, session=current_session
                )
                wall_ts = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                self._emit_pipeline_gate_signal_detected(
                    trace_id=cycle_trace_id,
                    decision_cycle_id=cycle_decision_id,
                    current_session=current_session,
                    regime=regime,
                    bar_timestamp=wall_ts,
                    eval_stage="regime_block",
                )
                self._emit_signal_evaluated(
                    trace_id=cycle_trace_id,
                    decision_cycle_id=cycle_decision_id,
                    direction="NONE",
                    confidence=0.0,
                    regime=regime,
                    setup=False,
                    eval_stage="regime_block",
                    decision_context=pre_ctx,
                )
                self._log_decision_cycle(
                    now=now,
                    action="no_trade",
                    reason="regime_block",
                    regime=regime,
                    killzone=current_session,
                    position_ok=position_ok,
                    daily_loss_ok=daily_loss_ok,
                )
                self._emit_trade_action(
                    trace_id=cycle_trace_id,
                    decision_cycle_id=cycle_decision_id,
                    decision="NO_ACTION",
                    reason="regime_block",
                    session=current_session,
                    regime=regime,
                    decision_context=pre_ctx,
                )
                return

            # Per-regime session/time filter
            if self._filter_session:
                allowed_sessions = rp.get("allowed_sessions")
                if allowed_sessions and current_session not in allowed_sessions:
                    logger.debug("Regime %s session %s not allowed", regime, current_session)
                    pre_ctx = self._runner_pre_signal_decision_context(
                        eval_stage="outside_killzone",
                        regime=regime,
                        session=current_session,
                        allowed_sessions=list(allowed_sessions),
                    )
                    wall_ts = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    self._emit_pipeline_gate_signal_detected(
                        trace_id=cycle_trace_id,
                        decision_cycle_id=cycle_decision_id,
                        current_session=current_session,
                        regime=regime,
                        bar_timestamp=wall_ts,
                        eval_stage="outside_killzone",
                    )
                    self._emit_signal_evaluated(
                        trace_id=cycle_trace_id,
                        decision_cycle_id=cycle_decision_id,
                        direction="NONE",
                        confidence=0.0,
                        regime=regime,
                        setup=False,
                        eval_stage="outside_killzone",
                        decision_context=pre_ctx,
                    )
                    self._log_decision_cycle(
                        now=now,
                        action="no_trade",
                        reason="outside_killzone",
                        regime=regime,
                        killzone=current_session,
                        position_ok=position_ok,
                        daily_loss_ok=daily_loss_ok,
                    )
                    self._emit_trade_action(
                        trace_id=cycle_trace_id,
                        decision_cycle_id=cycle_decision_id,
                        decision="NO_ACTION",
                        reason="outside_killzone",
                        session=current_session,
                        regime=regime,
                        decision_context=pre_ctx,
                    )
                    return

                min_hour = rp.get("min_hour_utc")
                if min_hour is not None and now.hour < min_hour:
                    logger.debug("Regime %s hour %d < min %d", regime, now.hour, min_hour)
                    pre_ctx = self._runner_pre_signal_decision_context(
                        eval_stage="time_filter_block",
                        regime=regime,
                        session=current_session,
                        min_hour_utc=min_hour,
                        hour_utc=now.hour,
                    )
                    wall_ts = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                    self._emit_pipeline_gate_signal_detected(
                        trace_id=cycle_trace_id,
                        decision_cycle_id=cycle_decision_id,
                        current_session=current_session,
                        regime=regime,
                        bar_timestamp=wall_ts,
                        eval_stage="time_filter_block",
                    )
                    self._emit_signal_evaluated(
                        trace_id=cycle_trace_id,
                        decision_cycle_id=cycle_decision_id,
                        direction="NONE",
                        confidence=0.0,
                        regime=regime,
                        setup=False,
                        eval_stage="time_filter_block",
                        decision_context=pre_ctx,
                    )
                    self._log_decision_cycle(
                        now=now,
                        action="no_trade",
                        reason="time_filter_block",
                        regime=regime,
                        killzone=current_session,
                        position_ok=position_ok,
                        daily_loss_ok=daily_loss_ok,
                    )
                    self._emit_trade_action(
                        trace_id=cycle_trace_id,
                        decision_cycle_id=cycle_decision_id,
                        decision="NO_ACTION",
                        reason="time_filter_block",
                        session=current_session,
                        regime=regime,
                        decision_context=pre_ctx,
                    )
                    return

        # Position limit
        if self._filter_position_limit and not position_ok:
            logger.debug("Position limit reached (%d)", self._max_open_positions)
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="position_limit_block",
                regime=regime,
                session=current_session,
                max_open_positions=self._max_open_positions,
            )
            wall_ts = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=wall_ts,
                eval_stage="position_limit_block",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="position_limit_block",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="position_limit_block",
                regime=regime,
                killzone=current_session,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="position_limit_block",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        # Daily loss limit
        if self._filter_daily_loss and not daily_loss_ok:
            logger.warning("Daily loss limit reached (%.2fR)", self._daily_pnl_r)
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="daily_loss_block",
                regime=regime,
                session=current_session,
                daily_pnl_r=float(self._daily_pnl_r),
            )
            wall_ts = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=wall_ts,
                eval_stage="daily_loss_block",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="daily_loss_block",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="daily_loss_block",
                regime=regime,
                killzone=current_session,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="daily_loss_block",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        # Load data and compute signals
        data_15m, source_actual = self._load_recent_data("15m", bars=300)
        if data_15m.empty or len(data_15m) < MIN_BARS_FOR_SIGNAL:
            symbol = self.cfg.get("symbol", "XAUUSD")
            last_ts = str(data_15m.index[-1]) if not data_15m.empty else "None"
            logger.warning(
                "signal_warmup_check symbol=%s timeframe=15m required=%d "
                "received=%d last_ts=%s source=%s_cache",
                symbol, MIN_BARS_FOR_SIGNAL, len(data_15m), last_ts,
                source_actual,
            )
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="bars_missing",
                regime=regime,
                session=current_session,
                source_actual=source_actual,
                bar_count=len(data_15m),
                min_bars=MIN_BARS_FOR_SIGNAL,
            )
            bar_anchor = (
                last_ts
                if not data_15m.empty
                else now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=bar_anchor,
                eval_stage="bars_missing",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="bars_missing",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="bars_missing",
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bars_ok=False,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="bars_missing",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        # Detect if we're on a new bar (cooldown filter)
        latest_ts = data_15m.index[-1]
        if self._filter_cooldown and self._last_bar_ts is not None and latest_ts <= self._last_bar_ts:
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="same_bar_already_processed",
                regime=regime,
                session=current_session,
                latest_bar_ts=str(latest_ts),
                last_processed_bar_ts=str(self._last_bar_ts),
            )
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=str(latest_ts),
                eval_stage="same_bar_already_processed",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="same_bar_already_processed",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="same_bar_already_processed",
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bars_ok=True,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="same_bar_already_processed",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return  # Already processed this bar
        if self._filter_cooldown:
            self._last_bar_ts = latest_ts

        # Compute SQE signals
        precomputed_df, last_idx, sqe_cfg, signals_to_check, long_signal, short_signal = (
            self._compute_sqe_signal_state(data_15m)
        )

        if not signals_to_check:
            logger.debug("No entry signals at %s", now.strftime("%H:%M"))
            long_ctx = sqe_decision_context_at_bar(precomputed_df, "LONG", last_idx, sqe_cfg)
            short_ctx = sqe_decision_context_at_bar(precomputed_df, "SHORT", last_idx, sqe_cfg)
            long_ctx["session"] = current_session
            short_ctx["session"] = current_session
            if regime is not None:
                long_ctx["regime"] = regime
                short_ctx["regime"] = regime
            pre_ctx = self._runner_pre_signal_decision_context(
                eval_stage="no_entry_signal",
                regime=regime,
                session=current_session,
                long=long_ctx,
                short=short_ctx,
                latest_bar_ts=str(data_15m.index[-1]),
                last_processed_bar_ts=str(self._last_bar_ts)
                if self._last_bar_ts is not None
                else None,
                source_actual=source_actual,
            )
            self._emit_pipeline_gate_signal_detected(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                current_session=current_session,
                regime=regime,
                bar_timestamp=str(data_15m.index[-1]),
                eval_stage="no_entry_signal",
            )
            self._emit_signal_evaluated(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                direction="NONE",
                confidence=0.0,
                regime=regime,
                setup=False,
                eval_stage="no_entry_signal",
                decision_context=pre_ctx,
            )
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="no_entry_signal",
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bars_ok=True,
                long_signal=long_signal,
                short_signal=short_signal,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            self._emit_trade_action(
                trace_id=cycle_trace_id,
                decision_cycle_id=cycle_decision_id,
                decision="NO_ACTION",
                reason="no_entry_signal",
                session=current_session,
                regime=regime,
                decision_context=pre_ctx,
            )
            return

        for direction in signals_to_check:
            trace_id = self._new_trace_id()
            signal_id = str(uuid4())
            dir_cycle_id = cycle_decision_id
            confidence = 1.0
            sqe_ctx = sqe_decision_context_at_bar(precomputed_df, direction, last_idx, sqe_cfg)
            sqe_ctx["session"] = current_session
            if regime is not None:
                sqe_ctx["regime"] = regime
            mod_keys = ("mss_confirmed", "sweep_detected", "fvg_in_zone", "displacement_trigger")
            modules_hint = {k: sqe_ctx[k] for k in mod_keys if k in sqe_ctx}
            self._emit_signal_detected(
                trace_id=trace_id,
                signal_id=signal_id,
                direction=direction,
                strength=confidence,
                bar_timestamp=str(data_15m.index[last_idx]),
                regime=regime,
                session=current_session,
                modules_hint=modules_hint or None,
                decision_cycle_id=dir_cycle_id,
            )
            emit_ctx = dict(sqe_ctx)
            emit_ctx["latest_bar_ts"] = str(data_15m.index[last_idx])
            try:
                emit_ctx["price_at_signal"] = float(data_15m["close"].iloc[last_idx])
            except (KeyError, TypeError, ValueError):
                pass
            sp_live = self._try_current_spread_pips()
            if sp_live is not None:
                emit_ctx["spread_pips"] = sp_live
            self._emit_signal_evaluated(
                trace_id=trace_id,
                direction=direction,
                confidence=confidence,
                regime=regime,
                decision_context=emit_ctx,
                decision_cycle_id=dir_cycle_id,
            )
            action, reason = self._evaluate_and_execute(
                direction,
                data_15m,
                now,
                regime,
                trace_id,
                current_session,
                strategy_decision_context=sqe_ctx,
                signal_id=signal_id,
                decision_cycle_id=dir_cycle_id,
            )
            self._log_decision_cycle(
                now=now,
                action=action,
                reason=reason,
                regime=regime,
                killzone=current_session,
                source_actual=source_actual,
                bias=direction.lower(),
                bars_ok=True,
                long_signal=long_signal,
                short_signal=short_signal,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )

    def _evaluate_and_execute(
        self,
        direction: str,
        data: pd.DataFrame,
        now: datetime,
        regime: Optional[str],
        trace_id: str,
        session: str,
        strategy_decision_context: Optional[Dict[str, Any]] = None,
        signal_id: Optional[str] = None,
        decision_cycle_id: Optional[str] = None,
    ) -> tuple[str, str]:
        """Run final checks and submit order for a signal."""
        strategy_decision_context = dict(strategy_decision_context or {})

        def _with_exec(ex: Dict[str, Any]) -> Dict[str, Any]:
            return {**strategy_decision_context, "execution": ex}

        regime_profiles = self.cfg.get("regime_profiles", {})
        rp = regime_profiles.get(regime, {}) if regime else {}
        llm_execution: Optional[Dict[str, Any]] = None

        # NewsGate check
        news_boost = 1.0
        if self._news_gate and self._filter_news:
            gate_result = self._news_gate.check_gate(now, direction)
            if not gate_result["allowed"]:
                logger.info("NewsGate blocks %s: %s", direction, gate_result["reason"])
                self._emit_guard_decision(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="BLOCK",
                    reason="news_block",
                    guard_name="news_gate",
                    session=session,
                    regime=regime,
                )
                self._emit_trade_action(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="NO_ACTION",
                    reason="news_block",
                    side=direction,
                    session=session,
                    regime=regime,
                    decision_context=_with_exec(
                        {"blocked_by": "news_block", "detail": gate_result.get("reason")}
                    ),
                )
                if signal_id:
                    self._emit_signal_filtered(
                        trace_id=trace_id, signal_id=signal_id, raw_reason="news_block"
                    )
                return "no_trade", "news_block"
            news_boost = gate_result.get("boost", 1.0)

        # LLM advisory layer (optional): final decision support after gate check.
        if self._llm_advisor and self._llm_advisor.enabled:
            sentiment_summary = (
                self._news_gate.get_current_sentiment_summary()
                if self._news_gate
                else {"direction": "neutral", "avg_impact": 0.0, "event_count": 0}
            )
            advice = self._llm_advisor.evaluate(
                now=now,
                direction=direction,
                regime=regime,
                sentiment_summary=sentiment_summary,
                recent_events=self._recent_news_events,
            )
            if not advice.get("allowed", True):
                logger.info(
                    "LLM advisor blocks %s: %s (method=%s stance=%s conf=%.2f)",
                    direction,
                    advice.get("reason", "unknown"),
                    advice.get("method", "unknown"),
                    advice.get("stance", "neutral"),
                    float(advice.get("confidence", 0.0)),
                )
                self._emit_guard_decision(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="BLOCK",
                    reason="llm_advice_block",
                    guard_name="llm_advisor",
                    session=session,
                    regime=regime,
                    observed_value=float(advice.get("confidence", 0.0)),
                )
                self._emit_trade_action(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="NO_ACTION",
                    reason="llm_advice_block",
                    side=direction,
                    session=session,
                    regime=regime,
                    decision_context=_with_exec(
                        {
                            "blocked_by": "llm_advice_block",
                            "detail": advice.get("reason", "unknown"),
                        }
                    ),
                )
                if signal_id:
                    self._emit_signal_filtered(
                        trace_id=trace_id, signal_id=signal_id, raw_reason="llm_advice_block"
                    )
                return "no_trade", "llm_advice_block"
            advice_mult = float(advice.get("risk_multiplier", 1.0) or 1.0)
            news_boost *= advice_mult
            llm_execution = {
                "method": str(advice.get("method", "unknown")),
                "stance": str(advice.get("stance", "neutral")),
                "confidence": float(advice.get("confidence", 0.0)),
                "risk_multiplier": float(advice.get("risk_multiplier", 1.0) or 1.0),
            }
            logger.info(
                "LLM advisor %s: mult=%.2f (method=%s stance=%s conf=%.2f reason=%s)",
                direction,
                advice_mult,
                advice.get("method", "unknown"),
                advice.get("stance", "neutral"),
                float(advice.get("confidence", 0.0)),
                advice.get("reason", "n/a"),
            )

        # Spread guard
        spread_issue = self._check_spread_guard() if self._filter_spread else None
        if spread_issue:
            code = str(spread_issue.get("code") or "spread_block")
            detail_msg = str(spread_issue.get("detail") or code)
            logger.info("Spread guard blocks entry: %s", detail_msg)
            thr_raw = spread_issue.get("threshold")
            obs_raw = spread_issue.get("observed")
            thr_v = float(thr_raw) if isinstance(thr_raw, (int, float)) else None
            obs_v = float(obs_raw) if isinstance(obs_raw, (int, float)) else None
            guard_nm = "price_feed" if code == "price_unavailable" else "spread_guard"
            internal_reason = "price_unavailable" if code == "price_unavailable" else "spread_block"
            raw_filter = "price_unavailable" if code == "price_unavailable" else "spread_block"
            self._emit_guard_decision(
                trace_id=trace_id,
                decision_cycle_id=decision_cycle_id,
                decision="BLOCK",
                reason=internal_reason,
                guard_name=guard_nm,
                threshold=thr_v,
                observed_value=obs_v,
                session=session,
                regime=regime,
            )
            self._emit_trade_action(
                trace_id=trace_id,
                decision_cycle_id=decision_cycle_id,
                decision="NO_ACTION",
                reason=internal_reason,
                side=direction,
                session=session,
                regime=regime,
                decision_context=_with_exec({"blocked_by": internal_reason, "detail": detail_msg}),
            )
            if signal_id:
                self._emit_signal_filtered(
                    trace_id=trace_id, signal_id=signal_id, raw_reason=raw_filter
                )
            return "no_trade", internal_reason

        # Calculate SL/TP from ATR
        entry_atr = self._current_atr
        if entry_atr <= 0:
            _atr_series = compute_atr(data, period=14)
            entry_atr = float(_atr_series.iloc[-1]) if not _atr_series.empty else 0
        if entry_atr <= 0:
            logger.warning("ATR is 0 — cannot calculate SL/TP")
            self._emit_guard_decision(
                trace_id=trace_id,
                decision_cycle_id=decision_cycle_id,
                decision="BLOCK",
                reason="atr_unavailable",
                guard_name="atr_guard",
                session=session,
                regime=regime,
                threshold=0.0,
                observed_value=float(entry_atr),
            )
            self._emit_trade_action(
                trace_id=trace_id,
                decision_cycle_id=decision_cycle_id,
                decision="NO_ACTION",
                reason="atr_unavailable",
                side=direction,
                session=session,
                regime=regime,
                decision_context=_with_exec({"blocked_by": "atr_unavailable"}),
            )
            if signal_id:
                self._emit_signal_filtered(
                    trace_id=trace_id, signal_id=signal_id, raw_reason="atr_unavailable"
                )
            return "no_trade", "atr_unavailable"

        tp_r = rp.get("tp_r", self.cfg.get("backtest", {}).get("tp_r", 2.0))
        sl_r = rp.get("sl_r", self.cfg.get("backtest", {}).get("sl_r", 1.0))

        # Get current price
        if not self.dry_run and self.broker.is_connected:
            price_info = self.broker.get_current_price()
            if not price_info:
                logger.warning("Cannot get current price for order")
                self._emit_guard_decision(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="BLOCK",
                    reason="price_unavailable",
                    guard_name="price_feed",
                    session=session,
                    regime=regime,
                )
                self._emit_trade_action(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="NO_ACTION",
                    reason="price_unavailable",
                    side=direction,
                    session=session,
                    regime=regime,
                    decision_context=_with_exec({"blocked_by": "price_unavailable"}),
                )
                if signal_id:
                    self._emit_signal_filtered(
                        trace_id=trace_id, signal_id=signal_id, raw_reason="price_unavailable"
                    )
                return "no_trade", "price_unavailable"
            entry_price = price_info["ask"] if direction == "LONG" else price_info["bid"]
        else:
            entry_price = float(data["close"].iloc[-1])

        if direction == "LONG":
            sl = entry_price - sl_r * entry_atr
            tp = entry_price + tp_r * entry_atr
        else:
            sl = entry_price + sl_r * entry_atr
            tp = entry_price - tp_r * entry_atr

        # Position sizing
        risk_cfg = self.cfg.get("risk", {})
        risk_pct = risk_cfg.get("max_position_pct", 1.0)
        size_mult = rp.get("position_size_mult", 1.0) * news_boost
        units = self._calculate_units(entry_price, sl, risk_pct * size_mult)

        if units <= 0:
            logger.warning("Position size is 0 — skipping")
            self._emit_guard_decision(
                trace_id=trace_id,
                decision_cycle_id=decision_cycle_id,
                decision="BLOCK",
                reason="risk_block",
                guard_name="position_sizing",
                session=session,
                regime=regime,
                threshold=0.0,
                observed_value=float(units),
            )
            self._emit_trade_action(
                trace_id=trace_id,
                decision_cycle_id=decision_cycle_id,
                decision="NO_ACTION",
                reason="risk_block",
                side=direction,
                session=session,
                regime=regime,
                decision_context=_with_exec({"blocked_by": "risk_block"}),
            )
            if signal_id:
                self._emit_signal_filtered(
                    trace_id=trace_id, signal_id=signal_id, raw_reason="risk_block"
                )
            return "no_trade", "risk_block"

        logger.info(
            "SIGNAL: %s %s @ %.2f | SL: %.2f | TP: %.2f | ATR: %.2f | Regime: %s | Units: %.0f",
            direction, self.cfg.get("symbol", "XAUUSD"), entry_price, sl, tp,
            entry_atr, regime, units,
        )

        # Execute order
        if self.dry_run:
            logger.info("[DRY RUN] Would submit %s order: %.0f units @ %.2f", direction, units, entry_price)
            trade_id = f"DRY_{now.strftime('%Y%m%d_%H%M%S')}_{direction}"
            fill_price = entry_price
        else:
            request = ExecutionRequest(
                symbol=self.cfg.get("broker", {}).get("instrument", "XAU_USD"),
                side=direction,
                entry=entry_price,
                stop_loss=sl,
                take_profit=tp,
                risk_percent=risk_pct * size_mult,
                account_id=self._account_id,
                units=units,
                comment=f"SQE_{direction}_{regime or 'NA'}",
            )

            try:
                exec_result = self.quantbridge.execute(request)
            except Exception as e:
                logger.error("QuantBridge execution failed: %s", e)
                self._emit_guard_decision(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="BLOCK",
                    reason="execution_exception",
                    guard_name="quantbridge_execution",
                    session=session,
                    regime=regime,
                )
                self._emit_trade_action(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="NO_ACTION",
                    reason="execution_exception",
                    side=direction,
                    session=session,
                    regime=regime,
                    decision_context=_with_exec({"blocked_by": "execution_exception"}),
                )
                if signal_id:
                    self._emit_signal_filtered(
                        trace_id=trace_id, signal_id=signal_id, raw_reason="execution_exception"
                    )
                return "no_trade", "execution_exception"

            if exec_result.status != "filled":
                logger.error("Order failed via QuantBridge: %s", exec_result.message)
                self._emit_guard_decision(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="BLOCK",
                    reason="execution_reject",
                    guard_name="quantbridge_execution",
                    session=session,
                    regime=regime,
                )
                self._emit_trade_action(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="NO_ACTION",
                    reason="execution_reject",
                    side=direction,
                    session=session,
                    regime=regime,
                    decision_context=_with_exec(
                        {"blocked_by": "execution_reject", "detail": str(exec_result.message)}
                    ),
                )
                if signal_id:
                    self._emit_signal_filtered(
                        trace_id=trace_id, signal_id=signal_id, raw_reason="execution_reject"
                    )
                return "no_trade", "execution_reject"

            trade_id = exec_result.broker_order_id or f"UNK_{now.strftime('%H%M%S')}"
            fill_price = exec_result.filled_price or entry_price

            # Slippage check
            slippage = abs(fill_price - entry_price)
            risk_amount = abs(entry_price - sl)
            if risk_amount > 0 and (slippage / risk_amount) > self._max_slippage_r:
                logger.warning(
                    "Slippage too high: %.2f (%.1f%% of risk) — closing trade",
                    slippage, 100 * slippage / risk_amount,
                )
                self.broker.close_trade(trade_id)
                try:
                    slip_pr = calculate_rr(entry_price, float(fill_price), sl, direction)
                except Exception:
                    slip_pr = 0.0
                self._emit_trade_closed(
                    trade_id=trade_id,
                    exit_price=float(fill_price),
                    pnl_r=float(slip_pr),
                    outcome="slippage_flatten",
                    exit_tag="slippage_guard",
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    session=session,
                    regime=regime,
                    direction=direction,
                    pnl_abs=0.0,
                )
                slip_ratio = float(slippage / risk_amount) if risk_amount > 0 else 0.0
                self._emit_guard_decision(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="BLOCK",
                    reason="slippage_block",
                    guard_name="slippage_guard",
                    session=session,
                    regime=regime,
                    threshold=float(self._max_slippage_r),
                    observed_value=slip_ratio,
                )
                self._emit_trade_action(
                    trace_id=trace_id,
                    decision_cycle_id=decision_cycle_id,
                    decision="NO_ACTION",
                    reason="slippage_block",
                    side=direction,
                    session=session,
                    regime=regime,
                    decision_context=_with_exec({"blocked_by": "slippage_block"}),
                )
                if signal_id:
                    self._emit_signal_filtered(
                        trace_id=trace_id, signal_id=signal_id, raw_reason="slippage_block"
                    )
                return "no_trade", "slippage_block"

        # Register with order manager
        self.order_manager.register_trade(
            trade_id=trade_id, instrument=self.cfg.get("symbol", "XAUUSD"),
            direction=direction, entry_price=fill_price, units=units,
            sl=sl, tp=tp, atr=entry_atr, regime=regime or "",
            requested_price=entry_price,
        )

        # Register with position monitor
        pos = Position(
            trade_id=trade_id,
            instrument=self.cfg.get("symbol", "XAUUSD"),
            direction=direction,
            entry_price=fill_price,
            units=units,
            sl=sl, tp=tp,
            open_time=now,
            atr_at_entry=entry_atr,
            regime_at_entry=regime or "",
            thesis=f"SQE {direction} in {regime or 'unknown'} regime",
        )
        self.position_monitor.add_position(pos)
        self._daily_trade_count += 1
        self._register_open_trade_quantlog(
            trade_id,
            trace_id=trace_id,
            decision_cycle_id=decision_cycle_id,
            session=session,
            regime=regime,
            direction=direction,
            entry_price=float(fill_price),
            signal_id=signal_id,
        )

        logger.info("Trade registered: %s %s (id=%s)", direction, regime, trade_id)
        if self._telegram.enabled:
            self._telegram.alert_trade_entry(
                direction=direction,
                symbol=self.cfg.get("symbol", "XAUUSD"),
                entry_price=fill_price,
                sl=sl,
                tp=tp,
                reason=f"regime={regime or 'none'}",
            )
        enter_exec: Dict[str, Any] = {
            "news_gate": "CLEAR",
            "news_boost": float(news_boost),
        }
        if llm_execution is not None:
            enter_exec["llm"] = llm_execution
        enter_ctx = _with_exec(enter_exec)
        if self.dry_run:
            self._emit_trade_action(
                trace_id=trace_id,
                decision_cycle_id=decision_cycle_id,
                decision="ENTER",
                reason="all_conditions_met",
                side=direction,
                session=session,
                regime=regime,
                decision_context=enter_ctx,
                trade_id=trade_id,
            )
            self._emit_trade_executed(
                trace_id=trace_id,
                signal_id=signal_id,
                direction=direction,
                trade_id=trade_id,
                regime=regime,
                session=session,
                decision_cycle_id=decision_cycle_id,
            )
            return "order_intent", "all_conditions_met"
        self._emit_trade_action(
            trace_id=trace_id,
            decision_cycle_id=decision_cycle_id,
            decision="ENTER",
            reason="all_conditions_met",
            side=direction,
            session=session,
            regime=regime,
            decision_context=enter_ctx,
            trade_id=trade_id,
        )
        self._emit_trade_executed(
            trace_id=trace_id,
            signal_id=signal_id,
            direction=direction,
            trade_id=trade_id,
            regime=regime,
            session=session,
            decision_cycle_id=decision_cycle_id,
        )
        return "order_filled", "all_conditions_met"

    def _calculate_units(self, entry: float, sl: float, risk_pct: float) -> float:
        """Calculate position size based on account equity and risk percentage."""
        risk_amount_per_unit = abs(entry - sl)
        if risk_amount_per_unit <= 0:
            return 0.0

        if not self.dry_run and self.broker.is_connected:
            acct = self.broker.get_account_info()
            if acct:
                risk_usd = acct.equity * (risk_pct / 100.0)
                return max(1, round(risk_usd / risk_amount_per_unit))

        # Dry run default: assume $10k account
        default_equity = self.cfg.get("risk", {}).get("paper_equity", 10000.0)
        risk_usd = default_equity * (risk_pct / 100.0)
        return max(1, round(risk_usd / risk_amount_per_unit))

    # ── News Polling ──────────────────────────────────────────────────

    def _poll_news(self):
        if not self._news_poller:
            return
        try:
            events = self._news_poller.poll()
            if self._relevance_filter:
                events = self._relevance_filter.filter_batch(events)
            events = self._select_news_events_for_processing(events, datetime.now(timezone.utc))
            alerts_sent = 0

            for event in events:
                self._recent_news_events.append(event)
                if len(self._recent_news_events) > 200:
                    self._recent_news_events = self._recent_news_events[-200:]
                classification = (
                    self._gold_classifier.classify(event)
                    if hasattr(self, "_gold_classifier")
                    else None
                )
                sentiment = self._analyze_sentiment_with_budget(event)

                if (
                    self._news_telegram_enabled
                    and sentiment
                    and self._telegram.enabled
                    and alerts_sent < self._news_telegram_max_alerts_per_poll
                    and abs(float(sentiment.impact_on_gold)) >= self._news_telegram_min_abs_impact
                ):
                    cls_text = ""
                    if classification:
                        cls_text = f"{classification.niche}/{classification.event_type}"
                    sent_ok = self._telegram.alert_news_event(
                        headline=event.headline,
                        source=event.source_name,
                        sentiment=sentiment.direction,
                        impact=float(sentiment.impact_on_gold),
                        classification=cls_text,
                    )
                    if sent_ok:
                        alerts_sent += 1

                if self._news_gate and sentiment:
                    self._news_gate.add_news_event(event, sentiment)

                if self._news_history and sentiment:
                    self._news_history.add_event(event, sentiment)

                if self._counter_news and sentiment:
                    positions = self.position_monitor.all_positions
                    if positions:
                        affected = self._counter_news.check_against_positions(event, positions)
                        for hit in affected:
                            if hit["action"] == "exit":
                                self.position_monitor.invalidate_thesis(
                                    hit["trade_id"], hit["reason"],
                                )

                if classification:
                    logger.info(
                        "News: [%s/%s] %s | sentiment: %s",
                        classification.niche, classification.event_type,
                        event.headline[:60],
                        sentiment.direction if sentiment else "?",
                    )
        except Exception as e:
            logger.error("News poll error: %s", e)

    def _select_news_events_for_processing(
        self,
        events: list,
        now: datetime,
    ) -> list:
        if not events:
            return events

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        fresh_events = []
        stale_dropped = 0
        for event in events:
            ts = event.published_at or event.received_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_minutes = (now - ts).total_seconds() / 60.0
            if age_minutes <= self._news_max_event_age_minutes:
                fresh_events.append(event)
            else:
                stale_dropped += 1

        if stale_dropped > 0:
            logger.info(
                "News budget: dropped %d stale events (> %d min)",
                stale_dropped,
                self._news_max_event_age_minutes,
            )

        if len(fresh_events) <= self._news_max_events_per_poll:
            return fresh_events

        prioritized = sorted(
            fresh_events,
            key=lambda e: (
                int(e.source_tier),
                -len(e.topic_hints),
                e.received_at,
            ),
        )[: self._news_max_events_per_poll]

        dropped_for_budget = len(fresh_events) - len(prioritized)
        logger.info(
            "News budget: processing %d events, dropped %d by poll cap",
            len(prioritized),
            dropped_for_budget,
        )
        return prioritized

    def _analyze_sentiment_with_budget(self, event):
        if not self._sentiment_engine:
            return None
        try:
            event_tier = int(event.source_tier)
        except Exception:
            event_tier = 4

        if event_tier > self._news_max_source_tier_for_llm and self._rule_sentiment_engine:
            return self._rule_sentiment_engine.analyze(event)
        return self._sentiment_engine.analyze(event)

    def _update_news_regime_override(self):
        """Use news state to override technical regime when appropriate."""
        if not self._news_gate:
            self._news_regime_override = None
            return

        now = datetime.now(timezone.utc)
        for evt in self._news_gate._scheduled_events:
            evt_time = evt["time"]
            if evt_time.tzinfo is None:
                evt_time = evt_time.replace(tzinfo=timezone.utc)
            if evt["name"] in self._news_gate._high_impact_events:
                window_start = evt_time - timedelta(minutes=60)
                window_end = evt_time + timedelta(minutes=30)
                if window_start <= now <= window_end:
                    self._news_regime_override = REGIME_EXPANSION
                    logger.info(
                        "News regime override -> EXPANSION (high-impact: %s)", evt["name"],
                    )
                    return

        summary = self._news_gate.get_current_sentiment_summary()
        if summary["event_count"] >= 3 and abs(summary["avg_impact"]) > 0.5:
            self._news_regime_override = None
            logger.debug("Strong news sentiment (%.2f) — technical regime stands", summary["avg_impact"])
            return

        self._news_regime_override = None

    # ── Position Monitoring ───────────────────────────────────────────

    def _monitor_positions(self):
        """Check open positions: close invalid thesis, update order manager."""
        for pos in list(self.position_monitor.all_positions):
            if not pos.thesis_valid:
                logger.warning("Position %s thesis invalid — closing", pos.trade_id)
                if not self.dry_run and self.broker.is_connected:
                    self.broker.close_trade(pos.trade_id)
                removed = self.position_monitor.remove_position(pos.trade_id)
                self.order_manager.unregister_trade(pos.trade_id, reason="thesis_invalid")
                if removed is not None:
                    ex = float(removed.current_price or removed.entry_price)
                    try:
                        pr = calculate_rr(removed.entry_price, ex, removed.sl, removed.direction.value)
                    except Exception:
                        pr = 0.0
                    self._emit_trade_closed(
                        trade_id=pos.trade_id,
                        exit_price=ex,
                        pnl_r=float(pr),
                        outcome="thesis_invalid",
                        exit_tag="risk_exit",
                        pnl_abs=float(removed.unrealized_pnl),
                        direction=removed.direction.value,
                    )

    def _send_status_report(self, now: datetime, reason: str = "interval") -> None:
        if not self._telegram.enabled:
            return
        if reason == "interval" and (now - self._last_status_report).total_seconds() < self._report_interval_seconds:
            return

        mode = "DRY_RUN" if self.dry_run else "LIVE"
        regime = self.get_effective_regime() or "none"
        open_positions = len(self.position_monitor.open_positions)
        broker_positions: Optional[int] = None
        account_balance: Optional[float] = None
        account_equity: Optional[float] = None
        account_unrealized_pnl: Optional[float] = None
        account_daily_pnl: Optional[float] = None
        account_daily_baseline_at: Optional[str] = None
        account_currency: str = "USD"
        if not self.dry_run and self.broker.is_connected:
            try:
                broker_positions = len(self.broker.get_open_trades(instrument=None))
            except Exception as e:
                logger.warning("Failed to fetch broker open trades for status report: %s", e)
            try:
                acct = self.broker.get_account_info()
                if acct is not None:
                    account_balance = float(acct.balance)
                    account_equity = float(acct.equity)
                    account_unrealized_pnl = float(acct.unrealized_pnl)
                    account_currency = str(acct.currency or "USD")
                    account_daily_pnl = self._update_daily_account_baseline(now, account_equity)
                    account_daily_baseline_at = self._daily_account_baseline_set_at
                    if broker_positions is None:
                        broker_positions = int(acct.open_trade_count)
            except Exception as e:
                logger.warning("Failed to fetch broker account state for status report: %s", e)
        mins = max(1, self._report_interval_seconds // 60)
        activity_caption = {
            "startup": "Activity since process start",
            "shutdown": "Activity since last report (shutdown)",
            "interval": f"Activity past ~{mins} min",
        }.get(reason, "Activity since last report")

        bar_lag = self._bar_lag_minutes(now)
        sent = self._telegram.alert_status_report(
            symbol=self.cfg.get("symbol", "XAUUSD"),
            mode=mode,
            regime=regime,
            trades_today=self._daily_trade_count,
            pnl_r=self._daily_pnl_r,
            open_positions=open_positions,
            source=self._last_data_source,
            broker_positions=broker_positions,
            account_daily_pnl=account_daily_pnl,
            account_daily_baseline_at=account_daily_baseline_at,
            account_balance=account_balance,
            account_equity=account_equity,
            account_unrealized_pnl=account_unrealized_pnl,
            account_currency=account_currency,
            hourly_no_action=dict(self._hourly_no_action_counts),
            hourly_enter=self._hourly_enter_count,
            hourly_signal_eval_new_bar=self._hourly_signal_eval_new_bar,
            hourly_signal_eval_same_bar=self._hourly_signal_eval_same_bar,
            activity_caption=activity_caption,
            telemetry_eval_stage=self._telemetry_eval_stage,
            telemetry_latest_bar_ts=self._telemetry_latest_bar_ts,
            telemetry_last_processed_bar_ts=self._telemetry_last_processed_bar_ts,
            telemetry_source_actual=self._telemetry_source_actual,
            bar_lag_minutes=bar_lag,
        )
        if sent:
            self._last_status_report = now
            self._hourly_no_action_counts.clear()
            self._hourly_enter_count = 0
            self._hourly_signal_eval_new_bar = 0
            self._hourly_signal_eval_same_bar = 0
            logger.info("Telegram status report sent (%s)", reason)

    # ── Main Loop ─────────────────────────────────────────────────────

    def run(self):
        """Main loop: connect, bootstrap data, update regime, check signals, manage positions."""
        mode = "DRY RUN" if self.dry_run else "LIVE"
        logger.info("Starting LiveRunner in %s mode", mode)

        data_source = str(self.cfg.get("data", {}).get("source", "auto")).lower()
        connect_for_market_data = self.dry_run and data_source == "ctrader"
        if (not self.dry_run) or connect_for_market_data:
            if not self.broker.connect():
                logger.error("Cannot connect to broker. Exiting.")
                return

        if not self._bootstrap_market_data():
            logger.error(
                "market_data_bootstrap_failed — no point running with 0 bars. "
                "Check source config, symbol mapping, data provider availability, "
                "and data/market_cache path."
            )
            if not self.dry_run and self.broker.is_connected:
                self.broker.disconnect()
            return

        self.order_manager.load_state()
        self._load_daily_account_state()
        self._sync_positions_from_broker()

        # Prime regime before first startup report so Telegram does not start at "none".
        data_15m, _ = self._load_recent_data("15m", 300)
        data_1h, _ = self._load_recent_data("1h", 100)
        self._update_regime(data_15m, data_1h if not data_1h.empty else None)

        if self._telegram.enabled and self._telegram.startup_report_enabled():
            self._send_status_report(datetime.now(timezone.utc), reason="startup")

        self._running = True
        signal.signal(signal.SIGINT, self._handle_shutdown)

        check_interval = self.cfg.get("execution", {}).get("check_interval_seconds", 60)
        regime_interval = self.cfg.get("execution", {}).get("regime_update_seconds", 900)
        news_interval = self.cfg.get("news", {}).get("poll_interval_seconds", 30)
        last_news_poll = datetime.min.replace(tzinfo=timezone.utc)

        try:
            while self._running:
                now = datetime.now(timezone.utc)
                self._reset_daily_tracking(now)

                # Update regime periodically
                if (now - self._last_regime_update).total_seconds() >= regime_interval:
                    data_15m, _ = self._load_recent_data("15m", 300)
                    data_1h, _ = self._load_recent_data("1h", 100)
                    self._update_regime(data_15m, data_1h if not data_1h.empty else None)

                # Poll news
                if self._news_poller and (now - last_news_poll).total_seconds() >= news_interval:
                    self._poll_news()
                    self._update_news_regime_override()
                    last_news_poll = now

                # Sync positions from broker
                self._sync_positions_from_broker()

                # Check signals in entry sessions
                session_mode = self.cfg.get("backtest", {}).get("session_mode", "killzone")
                session = session_from_timestamp(now, mode=session_mode)
                if session in ENTRY_SESSIONS:
                    self._check_signals(now)
                    self._maybe_emit_market_data_stale_warning(now, session)

                # Monitor positions
                self._monitor_positions()
                self._send_status_report(now, reason="interval")

                time.sleep(check_interval)

        except KeyboardInterrupt:
            pass
        except Exception as e:
            logger.exception("Live runner crashed: %s", e)
            if self._telegram.enabled:
                self._telegram.alert_error("runtime_exception", str(e))
            raise
        finally:
            self._shutdown()

    def _handle_shutdown(self, signum, frame):
        logger.info("Shutdown signal received")
        self._running = False

    def _shutdown(self):
        logger.info("Shutting down LiveRunner...")
        if self._telegram.enabled and self._telegram.shutdown_report_enabled():
            self._send_status_report(datetime.now(timezone.utc), reason="shutdown")
        self.order_manager.save_state()
        if self._news_history:
            self._news_history.save_to_parquet()
            self._news_history.save_latest_json()
            logger.info("News history saved (%d events)", self._news_history.event_count)
        if self.broker.is_connected:
            self.broker.disconnect()
        logger.info("LiveRunner stopped.")
