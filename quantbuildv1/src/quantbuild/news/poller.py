"""News poller — orchestrates all sources, normalizes, yields new events."""
import logging
from typing import Any

from src.quantbuild.models.news_event import NormalizedNewsEvent
from src.quantbuild.news.base import NewsSource
from src.quantbuild.news.normalizer import NewsNormalizer
from src.quantbuild.news.rss import create_rss_sources
from src.quantbuild.news.newsapi_source import create_newsapi_source
from src.quantbuild.news.finnhub_source import create_finnhub_source

logger = logging.getLogger(__name__)


class NewsPoller:
    def __init__(self, cfg: dict[str, Any]):
        self._cfg = cfg
        self._sources: list[NewsSource] = []
        self._normalizer = NewsNormalizer(cfg)

    def setup(self) -> int:
        self._sources = []
        self._sources.extend(create_rss_sources(self._cfg))
        finnhub = create_finnhub_source(self._cfg)
        if finnhub:
            self._sources.append(finnhub)
        newsapi = create_newsapi_source(self._cfg)
        if newsapi:
            self._sources.append(newsapi)
        logger.info("NewsPoller initialized with %d sources", len(self._sources))
        return len(self._sources)

    def poll(self) -> list[NormalizedNewsEvent]:
        all_events: list[NormalizedNewsEvent] = []
        for source in self._sources:
            try:
                raw_items = source.fetch()
                events = self._normalizer.normalize_batch(raw_items, source.tier)
                new_events = [e for e in events if not e.is_duplicate]
                all_events.extend(new_events)
                logger.debug("Source %s: %d raw -> %d new", source.name, len(raw_items), len(new_events))
            except Exception:
                logger.exception("Failed to poll source %s", source.name)

        all_events.sort(key=lambda e: e.received_at)
        logger.info("Poll complete: %d new events from %d sources", len(all_events), len(self._sources))
        return all_events

    @property
    def source_count(self) -> int:
        return len(self._sources)

    @property
    def seen_count(self) -> int:
        return self._normalizer.seen_count
