"""Live runner — main loop for paper/live trading with news integration."""
import logging
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from src.quantbuild.config import load_config
from src.quantbuild.data.sessions import session_from_timestamp, ENTRY_SESSIONS
from src.quantbuild.execution.broker_oanda import OandaBroker
from src.quantbuild.execution.order_manager import OrderManager
from src.quantbuild.execution.position_monitor import PositionMonitor
from src.quantbuild.io.parquet_loader import load_parquet
from src.quantbuild.strategies.sqe_xauusd import get_sqe_default_config, _compute_modules_once, run_sqe_conditions

logger = logging.getLogger(__name__)


class LiveRunner:
    """Main live/paper trading loop."""

    def __init__(self, cfg: Dict[str, Any], dry_run: bool = True):
        self.cfg = cfg
        self.dry_run = dry_run
        self._running = False

        self.broker = OandaBroker(
            account_id=cfg.get("broker", {}).get("account_id", ""),
            token=cfg.get("broker", {}).get("token", ""),
            environment=cfg.get("broker", {}).get("environment", "practice"),
            instrument=cfg.get("broker", {}).get("instrument", "XAU_USD"),
        )
        self.order_manager = OrderManager(broker=self.broker if not dry_run else None, config=cfg.get("order_management"))
        self.position_monitor = PositionMonitor(cfg)

        self._news_poller = None
        self._news_gate = None
        self._sentiment_engine = None
        self._counter_news = None
        self._relevance_filter = None

        if cfg.get("news", {}).get("enabled", False):
            self._setup_news_layer()

    def _setup_news_layer(self):
        try:
            from src.quantbuild.news.poller import NewsPoller
            from src.quantbuild.news.relevance_filter import RelevanceFilter
            from src.quantbuild.news.gold_classifier import GoldEventClassifier
            from src.quantbuild.news.sentiment import HybridSentiment
            from src.quantbuild.news.counter_news import CounterNewsDetector
            from src.quantbuild.strategy_modules.news_gate import NewsGate

            self._news_poller = NewsPoller(self.cfg)
            self._news_poller.setup()
            self._relevance_filter = RelevanceFilter(self.cfg)
            self._gold_classifier = GoldEventClassifier(self.cfg)
            self._sentiment_engine = HybridSentiment(self.cfg)
            self._counter_news = CounterNewsDetector(self.cfg)
            self._news_gate = NewsGate(self.cfg)
            logger.info("News layer initialized: %d sources", self._news_poller.source_count)
        except Exception as e:
            logger.warning("News layer setup failed: %s", e)

    def run(self):
        """Main loop: connect, check signals, manage positions."""
        mode = "DRY RUN" if self.dry_run else "LIVE"
        logger.info("Starting LiveRunner in %s mode", mode)

        if not self.dry_run:
            if not self.broker.connect():
                logger.error("Cannot connect to broker. Exiting.")
                return

        self.order_manager.load_state()
        self._running = True
        signal.signal(signal.SIGINT, self._handle_shutdown)

        check_interval = 60
        news_interval = self.cfg.get("news", {}).get("poll_interval_seconds", 30)
        last_news_poll = datetime.min

        try:
            while self._running:
                now = datetime.now(timezone.utc)

                # Poll news
                if self._news_poller and (now - last_news_poll).total_seconds() >= news_interval:
                    self._poll_news()
                    last_news_poll = now

                # Check for new signals on each bar close
                session = session_from_timestamp(now, mode=self.cfg.get("backtest", {}).get("session_mode", "killzone"))
                if session in ENTRY_SESSIONS:
                    self._check_signals(now)

                # Monitor open positions
                self._monitor_positions()

                time.sleep(check_interval)

        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _poll_news(self):
        if not self._news_poller:
            return
        try:
            events = self._news_poller.poll()
            if self._relevance_filter:
                events = self._relevance_filter.filter_batch(events)

            for event in events:
                classification = self._gold_classifier.classify(event) if hasattr(self, '_gold_classifier') else None
                sentiment = self._sentiment_engine.analyze(event) if self._sentiment_engine else None

                if self._news_gate and sentiment:
                    self._news_gate.add_news_event(event, sentiment)

                if self._counter_news and sentiment:
                    positions = self.position_monitor.all_positions
                    if positions:
                        affected = self._counter_news.check_against_positions(event, positions)
                        for hit in affected:
                            if hit["action"] == "exit":
                                self.position_monitor.invalidate_thesis(hit["trade_id"], hit["reason"])

                if classification:
                    logger.info("News: [%s/%s] %s | sentiment: %s",
                                classification.niche, classification.event_type,
                                event.headline[:60], sentiment.direction if sentiment else "?")
        except Exception as e:
            logger.error("News poll error: %s", e)

    def _check_signals(self, now: datetime):
        logger.debug("Checking signals at %s", now.strftime("%H:%M"))

    def _monitor_positions(self):
        for pos in self.position_monitor.all_positions:
            if not pos.thesis_valid:
                logger.warning("Position %s thesis invalid — should close", pos.trade_id)

    def _handle_shutdown(self, signum, frame):
        logger.info("Shutdown signal received")
        self._running = False

    def _shutdown(self):
        logger.info("Shutting down LiveRunner...")
        self.order_manager.save_state()
        if self.broker.is_connected:
            self.broker.disconnect()
        logger.info("LiveRunner stopped.")
