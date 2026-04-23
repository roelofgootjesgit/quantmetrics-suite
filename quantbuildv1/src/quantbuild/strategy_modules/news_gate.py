"""News Gate — integrates news layer into the strategy pipeline.

Three levels:
  1. Gate/Filter: block entries around high-impact events
  2. Signal boost/suppress: adjust confidence based on news sentiment
  3. Counter-news: monitor open positions for contradicting news
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.quantbuild.models.news_event import NormalizedNewsEvent, SentimentResult
from src.quantbuild.models.signal import Signal

logger = logging.getLogger(__name__)


class NewsGate:
    """News-aware signal gate for XAUUSD trading."""

    def __init__(self, cfg: dict[str, Any]):
        gate_cfg = cfg.get("news", {}).get("gate", {})
        sentiment_cfg = cfg.get("news", {}).get("sentiment", {})

        self._block_before_min = gate_cfg.get("block_minutes_before_high_impact", 30)
        self._block_after_min = gate_cfg.get("block_minutes_after_high_impact", 15)
        self._high_impact_events = set(gate_cfg.get("high_impact_events", ["NFP", "FOMC", "CPI", "GDP"]))

        self._boost_threshold = sentiment_cfg.get("boost_threshold", 0.7)
        self._suppress_threshold = sentiment_cfg.get("suppress_threshold", 0.3)

        self._recent_events: list[NormalizedNewsEvent] = []
        self._recent_sentiments: dict[str, SentimentResult] = {}
        self._scheduled_events: list[dict] = []

    def add_scheduled_event(self, event_name: str, event_time: datetime) -> None:
        """Register a known upcoming economic event (e.g., FOMC at 18:00 UTC)."""
        self._scheduled_events.append({"name": event_name, "time": event_time})

    def add_news_event(self, event: NormalizedNewsEvent, sentiment: Optional[SentimentResult] = None) -> None:
        """Register a received news event with optional sentiment."""
        self._recent_events.append(event)
        if sentiment:
            self._recent_sentiments[event.event_id] = sentiment
        # Keep only last 100 events
        if len(self._recent_events) > 100:
            old = self._recent_events.pop(0)
            self._recent_sentiments.pop(old.event_id, None)

    def check_gate(self, timestamp: datetime, direction: str) -> dict:
        """
        Check if trading is allowed at this timestamp and direction.
        Returns: {"allowed": bool, "reason": str, "boost": float}
        """
        now = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)

        # Level 1: High-impact event gate
        for evt in self._scheduled_events:
            evt_time = evt["time"]
            if evt_time.tzinfo is None:
                evt_time = evt_time.replace(tzinfo=timezone.utc)
            if evt["name"] in self._high_impact_events:
                before_window = evt_time - timedelta(minutes=self._block_before_min)
                after_window = evt_time + timedelta(minutes=self._block_after_min)
                if before_window <= now <= after_window:
                    return {
                        "allowed": False,
                        "reason": f"Blocked: {evt['name']} at {evt_time.strftime('%H:%M')} UTC",
                        "boost": 0.0,
                    }

        # Level 2: Sentiment-based boost/suppress
        boost = 1.0
        recent_window = now - timedelta(minutes=30)
        relevant_sentiments = [
            s for eid, s in self._recent_sentiments.items()
            if self._event_in_window(eid, recent_window, now)
        ]

        if relevant_sentiments:
            avg_impact = sum(s.impact_on_gold for s in relevant_sentiments) / len(relevant_sentiments)
            avg_confidence = sum(s.confidence for s in relevant_sentiments) / len(relevant_sentiments)

            if direction == "LONG" and avg_impact > 0 and avg_confidence >= self._boost_threshold:
                boost = 1.0 + min(avg_impact * 0.5, 0.5)
                logger.info("News BOOST for LONG: %.2f (avg_impact=%.2f, avg_conf=%.2f)", boost, avg_impact, avg_confidence)
            elif direction == "LONG" and avg_impact < 0 and avg_confidence >= self._suppress_threshold:
                boost = max(0.3, 1.0 + avg_impact * 0.5)
                logger.info("News SUPPRESS for LONG: %.2f (bearish news)", boost)
            elif direction == "SHORT" and avg_impact < 0 and avg_confidence >= self._boost_threshold:
                boost = 1.0 + min(abs(avg_impact) * 0.5, 0.5)
                logger.info("News BOOST for SHORT: %.2f", boost)
            elif direction == "SHORT" and avg_impact > 0 and avg_confidence >= self._suppress_threshold:
                boost = max(0.3, 1.0 - avg_impact * 0.5)
                logger.info("News SUPPRESS for SHORT: %.2f (bullish news)", boost)

        return {"allowed": True, "reason": "OK", "boost": boost}

    def _event_in_window(self, event_id: str, start: datetime, end: datetime) -> bool:
        for evt in self._recent_events:
            if evt.event_id == event_id:
                t = evt.received_at
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                return start <= t <= end
        return False

    def get_current_sentiment_summary(self) -> dict:
        """Summarize current news sentiment state."""
        if not self._recent_sentiments:
            return {"direction": "neutral", "avg_impact": 0.0, "event_count": 0}

        sentiments = list(self._recent_sentiments.values())
        avg_impact = sum(s.impact_on_gold for s in sentiments) / len(sentiments)
        direction = "bullish" if avg_impact > 0.1 else ("bearish" if avg_impact < -0.1 else "neutral")
        return {
            "direction": direction,
            "avg_impact": avg_impact,
            "event_count": len(sentiments),
        }

    def clear(self) -> None:
        self._recent_events.clear()
        self._recent_sentiments.clear()
        self._scheduled_events.clear()
