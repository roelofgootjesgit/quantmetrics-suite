"""Historical news storage and replay for backtesting with news context."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.quantbuild.models.news_event import NormalizedNewsEvent, SourceTier, SentimentResult

logger = logging.getLogger(__name__)


class NewsHistory:
    """Store and replay historical news events for backtesting."""

    def __init__(self, cache_dir: Path = Path("data/news_cache")):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._events: list[NormalizedNewsEvent] = []
        self._sentiments: dict[str, SentimentResult] = {}

    def add_event(self, event: NormalizedNewsEvent, sentiment: Optional[SentimentResult] = None) -> None:
        self._events.append(event)
        if sentiment:
            self._sentiments[event.event_id] = sentiment

    def save_to_parquet(self, filename: str = "news_history.parquet") -> Path:
        """Save all events to Parquet for fast replay in backtests."""
        if not self._events:
            logger.warning("No events to save")
            return self._cache_dir / filename

        records = []
        for ev in self._events:
            sentiment = self._sentiments.get(ev.event_id)
            records.append({
                "event_id": ev.event_id,
                "timestamp": ev.received_at,
                "published_at": ev.published_at,
                "source_name": ev.source_name,
                "source_tier": ev.source_tier.value,
                "reliability": ev.source_reliability_score,
                "headline": ev.headline,
                "summary": ev.summary or "",
                "topic_hints": ",".join(ev.topic_hints),
                "category": ev.source_category,
                "sentiment_direction": sentiment.direction if sentiment else "",
                "sentiment_confidence": sentiment.confidence if sentiment else 0.0,
                "sentiment_impact": sentiment.impact_on_gold if sentiment else 0.0,
            })

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp")

        path = self._cache_dir / filename
        df.to_parquet(path, compression="snappy", index=False)
        logger.info("Saved %d news events to %s", len(records), path)
        return path

    def load_from_parquet(self, filename: str = "news_history.parquet") -> int:
        """Load historical events from Parquet."""
        path = self._cache_dir / filename
        if not path.exists():
            return 0

        df = pd.read_parquet(path)
        self._events = []
        self._sentiments = {}

        for _, row in df.iterrows():
            event = NormalizedNewsEvent(
                event_id=row["event_id"],
                received_at=row["timestamp"],
                published_at=row.get("published_at"),
                source_name=row["source_name"],
                source_tier=SourceTier(int(row["source_tier"])),
                source_reliability_score=float(row["reliability"]),
                headline=row["headline"],
                summary=row.get("summary") or None,
                topic_hints=row["topic_hints"].split(",") if row.get("topic_hints") else [],
                source_category=row.get("category", ""),
            )
            self._events.append(event)

            if row.get("sentiment_direction"):
                self._sentiments[event.event_id] = SentimentResult(
                    event_id=event.event_id,
                    direction=row["sentiment_direction"],
                    confidence=float(row.get("sentiment_confidence", 0)),
                    method="historical",
                    impact_on_gold=float(row.get("sentiment_impact", 0)),
                )

        logger.info("Loaded %d historical news events", len(self._events))
        return len(self._events)

    def save_latest_json(self, max_events: int = 50) -> Path:
        """Save latest events as JSON for the dashboard."""
        path = self._cache_dir / "latest_events.json"
        recent = sorted(self._events, key=lambda e: e.received_at, reverse=True)[:max_events]
        records = [e.model_dump(mode="json") for e in recent]
        path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
        return path

    def get_events_in_range(self, start: datetime, end: datetime) -> list[NormalizedNewsEvent]:
        """Get events within a time range (for backtest replay)."""
        start_utc = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end if end.tzinfo else end.replace(tzinfo=timezone.utc)

        return [
            ev for ev in self._events
            if start_utc <= (ev.received_at if ev.received_at.tzinfo else ev.received_at.replace(tzinfo=timezone.utc)) <= end_utc
        ]

    def get_sentiment_at(self, timestamp: datetime, lookback_minutes: int = 30) -> Optional[dict]:
        """Get aggregated sentiment around a timestamp (for backtest integration)."""
        from datetime import timedelta
        ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        window_start = ts - timedelta(minutes=lookback_minutes)

        relevant = []
        for ev in self._events:
            ev_ts = ev.received_at if ev.received_at.tzinfo else ev.received_at.replace(tzinfo=timezone.utc)
            if window_start <= ev_ts <= ts:
                sentiment = self._sentiments.get(ev.event_id)
                if sentiment:
                    relevant.append(sentiment)

        if not relevant:
            return None

        avg_impact = sum(s.impact_on_gold for s in relevant) / len(relevant)
        avg_confidence = sum(s.confidence for s in relevant) / len(relevant)
        direction = "bullish" if avg_impact > 0.1 else ("bearish" if avg_impact < -0.1 else "neutral")

        return {
            "direction": direction,
            "avg_impact": avg_impact,
            "avg_confidence": avg_confidence,
            "event_count": len(relevant),
        }

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def events(self) -> list[NormalizedNewsEvent]:
        return self._events
