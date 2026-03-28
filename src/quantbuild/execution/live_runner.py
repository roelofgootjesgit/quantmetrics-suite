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
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.quantbuild.config import load_config
from src.quantbuild.data.sessions import session_from_timestamp, ENTRY_SESSIONS
from src.quantbuild.alerts.telegram import TelegramAlerter
from src.quantbuild.execution.broker_factory import create_broker
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
from src.quantbuild.models.trade import Position
from src.quantbuild.strategies.sqe_xauusd import (
    get_sqe_default_config, _compute_modules_once, run_sqe_conditions,
)
from src.quantbuild.strategy_modules.regime.detector import (
    RegimeDetector, REGIME_EXPANSION, REGIME_COMPRESSION, REGIME_TREND,
)

logger = logging.getLogger(__name__)

MIN_BARS_FOR_SIGNAL = 100


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
        self._decision_cycle_n: int = 0
        self._report_interval_seconds: int = 3600
        self._last_status_report: datetime = datetime.min.replace(tzinfo=timezone.utc)
        self._last_data_source: str = "unknown"

        # Alerts/monitoring
        self._telegram = TelegramAlerter(cfg)
        self._report_interval_seconds = self._telegram.report_interval_seconds(default_seconds=3600)

        # News layer
        self._news_poller = None
        self._news_gate = None
        self._sentiment_engine = None
        self._counter_news = None
        self._relevance_filter = None
        self._news_history = None

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
            from src.quantbuild.news.sentiment import HybridSentiment
            from src.quantbuild.news.counter_news import CounterNewsDetector
            from src.quantbuild.news.history import NewsHistory
            from src.quantbuild.strategy_modules.news_gate import NewsGate

            self._news_poller = NewsPoller(self.cfg)
            self._news_poller.setup()
            self._relevance_filter = RelevanceFilter(self.cfg)
            self._gold_classifier = GoldEventClassifier(self.cfg)
            self._sentiment_engine = HybridSentiment(self.cfg)
            self._counter_news = CounterNewsDetector(self.cfg)
            self._news_gate = NewsGate(self.cfg)
            self._news_history = NewsHistory()
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

    def _check_spread_guard(self) -> Optional[str]:
        """Check if current spread is within acceptable range. Returns reason if blocked."""
        if self.dry_run:
            return None
        price_info = self.broker.get_current_price()
        if price_info is None:
            return "price_unavailable"
        spread = price_info.get("spread", 0)
        if spread > self._max_spread_pips:
            return f"spread_too_wide ({spread:.2f} > {self._max_spread_pips})"
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
            self.position_monitor.remove_position(mid)
            self.order_manager.unregister_trade(mid, reason="closed_by_broker")

        # Update prices
        for bt in broker_trades:
            self.position_monitor.update_price(bt.trade_id, bt.current_price)
            self.order_manager.update_price(bt.trade_id, bt.current_price)

    # ── Signal Evaluation ─────────────────────────────────────────────

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

    def _check_signals(self, now: datetime):
        """Evaluate SQE entry signals and submit orders when criteria are met."""
        regime = self.get_effective_regime()
        regime_profiles = self.cfg.get("regime_profiles", {})
        session_mode = self.cfg.get("backtest", {}).get("session_mode", "killzone")
        current_session = session_from_timestamp(now, mode=session_mode)
        position_ok = self._check_position_limit()
        daily_loss_ok = self._check_daily_loss_limit()

        # Regime skip
        if regime:
            rp = regime_profiles.get(regime, {})
            if rp.get("skip", False):
                logger.debug("Regime %s -> skip", regime)
                self._log_decision_cycle(
                    now=now,
                    action="no_trade",
                    reason="regime_block",
                    regime=regime,
                    killzone=current_session,
                    position_ok=position_ok,
                    daily_loss_ok=daily_loss_ok,
                )
                return

            # Per-regime session/time filter
            allowed_sessions = rp.get("allowed_sessions")
            if allowed_sessions and current_session not in allowed_sessions:
                logger.debug("Regime %s session %s not allowed", regime, current_session)
                self._log_decision_cycle(
                    now=now,
                    action="no_trade",
                    reason="outside_killzone",
                    regime=regime,
                    killzone=current_session,
                    position_ok=position_ok,
                    daily_loss_ok=daily_loss_ok,
                )
                return

            min_hour = rp.get("min_hour_utc")
            if min_hour is not None and now.hour < min_hour:
                logger.debug("Regime %s hour %d < min %d", regime, now.hour, min_hour)
                self._log_decision_cycle(
                    now=now,
                    action="no_trade",
                    reason="time_filter_block",
                    regime=regime,
                    killzone=current_session,
                    position_ok=position_ok,
                    daily_loss_ok=daily_loss_ok,
                )
                return

        # Position limit
        if not position_ok:
            logger.debug("Position limit reached (%d)", self._max_open_positions)
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="position_limit_block",
                regime=regime,
                killzone=current_session,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
            )
            return

        # Daily loss limit
        if not daily_loss_ok:
            logger.warning("Daily loss limit reached (%.2fR)", self._daily_pnl_r)
            self._log_decision_cycle(
                now=now,
                action="no_trade",
                reason="daily_loss_block",
                regime=regime,
                killzone=current_session,
                position_ok=position_ok,
                daily_loss_ok=daily_loss_ok,
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
            return

        # Detect if we're on a new bar
        latest_ts = data_15m.index[-1]
        if self._last_bar_ts is not None and latest_ts <= self._last_bar_ts:
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
            return  # Already processed this bar
        self._last_bar_ts = latest_ts

        # Compute SQE signals
        sqe_cfg = get_sqe_default_config()
        strategy_cfg = self.cfg.get("strategy", {}) or {}
        if strategy_cfg:
            from src.quantbuild.backtest.engine import _deep_merge
            _deep_merge(sqe_cfg, strategy_cfg)

        precomputed_df = _compute_modules_once(data_15m, sqe_cfg)
        long_entries = run_sqe_conditions(data_15m, "LONG", sqe_cfg, _precomputed_df=precomputed_df)
        short_entries = run_sqe_conditions(data_15m, "SHORT", sqe_cfg, _precomputed_df=precomputed_df)

        # Check the latest bar for signals
        last_idx = len(data_15m) - 1
        signals_to_check: List[str] = []
        if long_entries.iloc[last_idx]:
            signals_to_check.append("LONG")
        if short_entries.iloc[last_idx]:
            signals_to_check.append("SHORT")
        long_signal = bool(long_entries.iloc[last_idx])
        short_signal = bool(short_entries.iloc[last_idx])

        if not signals_to_check:
            logger.debug("No entry signals at %s", now.strftime("%H:%M"))
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
            return

        for direction in signals_to_check:
            action, reason = self._evaluate_and_execute(direction, data_15m, now, regime)
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
        self, direction: str, data: pd.DataFrame, now: datetime, regime: Optional[str],
    ) -> tuple[str, str]:
        """Run final checks and submit order for a signal."""
        regime_profiles = self.cfg.get("regime_profiles", {})
        rp = regime_profiles.get(regime, {}) if regime else {}

        # NewsGate check
        news_boost = 1.0
        if self._news_gate:
            gate_result = self._news_gate.check_gate(now, direction)
            if not gate_result["allowed"]:
                logger.info("NewsGate blocks %s: %s", direction, gate_result["reason"])
                return "no_trade", "news_block"
            news_boost = gate_result.get("boost", 1.0)

        # Spread guard
        spread_issue = self._check_spread_guard()
        if spread_issue:
            logger.info("Spread guard blocks entry: %s", spread_issue)
            return "no_trade", "spread_block"

        # Calculate SL/TP from ATR
        entry_atr = self._current_atr
        if entry_atr <= 0:
            _atr_series = compute_atr(data, period=14)
            entry_atr = float(_atr_series.iloc[-1]) if not _atr_series.empty else 0
        if entry_atr <= 0:
            logger.warning("ATR is 0 — cannot calculate SL/TP")
            return "no_trade", "atr_unavailable"

        tp_r = rp.get("tp_r", self.cfg.get("backtest", {}).get("tp_r", 2.0))
        sl_r = rp.get("sl_r", self.cfg.get("backtest", {}).get("sl_r", 1.0))

        # Get current price
        if not self.dry_run and self.broker.is_connected:
            price_info = self.broker.get_current_price()
            if not price_info:
                logger.warning("Cannot get current price for order")
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
                return "no_trade", "execution_exception"

            if exec_result.status != "filled":
                logger.error("Order failed via QuantBridge: %s", exec_result.message)
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
        if self.dry_run:
            return "order_intent", "all_conditions_met"
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

            for event in events:
                classification = (
                    self._gold_classifier.classify(event)
                    if hasattr(self, "_gold_classifier")
                    else None
                )
                sentiment = (
                    self._sentiment_engine.analyze(event)
                    if self._sentiment_engine
                    else None
                )

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
        for pos in self.position_monitor.all_positions:
            if not pos.thesis_valid:
                logger.warning("Position %s thesis invalid — closing", pos.trade_id)
                if not self.dry_run and self.broker.is_connected:
                    self.broker.close_trade(pos.trade_id)
                self.position_monitor.remove_position(pos.trade_id)
                self.order_manager.unregister_trade(pos.trade_id, reason="thesis_invalid")

    def _send_status_report(self, now: datetime, reason: str = "interval") -> None:
        if not self._telegram.enabled:
            return
        if reason == "interval" and (now - self._last_status_report).total_seconds() < self._report_interval_seconds:
            return

        mode = "DRY_RUN" if self.dry_run else "LIVE"
        regime = self.get_effective_regime() or "none"
        open_positions = len(self.position_monitor.open_positions)
        sent = self._telegram.alert_status_report(
            symbol=self.cfg.get("symbol", "XAUUSD"),
            mode=mode,
            regime=regime,
            trades_today=self._daily_trade_count,
            pnl_r=self._daily_pnl_r,
            open_positions=open_positions,
            source=self._last_data_source,
        )
        if sent:
            self._last_status_report = now
            logger.info("Telegram status report sent (%s)", reason)

    # ── Main Loop ─────────────────────────────────────────────────────

    def run(self):
        """Main loop: connect, bootstrap data, update regime, check signals, manage positions."""
        mode = "DRY RUN" if self.dry_run else "LIVE"
        logger.info("Starting LiveRunner in %s mode", mode)
        if self._telegram.enabled and self._telegram.startup_report_enabled():
            self._send_status_report(datetime.now(timezone.utc), reason="startup")

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
