"""RSS feed news source via feedparser."""
import logging
from datetime import datetime, timezone
from time import mktime
from typing import Any, Optional

import feedparser

from src.quantbuild.models.news_event import RawNewsItem, SourceTier
from src.quantbuild.news.base import NewsSource

logger = logging.getLogger(__name__)


class RSSSource(NewsSource):
    def __init__(self, feed_name: str, feed_url: str, tier: int = 2, category: str = ""):
        self._name = feed_name
        self._url = feed_url
        self._tier = SourceTier(tier)
        self._category = category
        self._etag: Optional[str] = None
        self._modified: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def tier(self) -> SourceTier:
        return self._tier

    @property
    def category(self) -> str:
        return self._category

    def fetch(self) -> list[RawNewsItem]:
        feed = feedparser.parse(self._url, etag=self._etag, modified=self._modified)
        if feed.get("status") == 304:
            return []
        self._etag = feed.get("etag")
        self._modified = feed.get("modified")

        items: list[RawNewsItem] = []
        for entry in feed.get("entries", []):
            item = _parse_entry(entry, self._name, self._category)
            if item:
                items.append(item)
        logger.debug("RSS %s: fetched %d items", self._name, len(items))
        return items


def _parse_entry(entry: dict[str, Any], source_name: str, category: str = "") -> Optional[RawNewsItem]:
    title = entry.get("title", "").strip()
    if not title:
        return None
    summary = entry.get("summary", "") or entry.get("description", "")
    link = entry.get("link", "")

    published_at = None
    for time_field in ("published_parsed", "updated_parsed"):
        parsed_time = entry.get(time_field)
        if parsed_time:
            try:
                published_at = datetime.fromtimestamp(mktime(parsed_time), tz=timezone.utc)
            except (ValueError, OverflowError):
                pass
            break

    return RawNewsItem(
        source_name=source_name, headline=title,
        body=summary if summary else None, url=link if link else None,
        published_at=published_at, raw_data={"id": entry.get("id", link)},
        source_category=category,
    )


def create_rss_sources(cfg: dict[str, Any]) -> list[RSSSource]:
    news_cfg = cfg.get("news", {})
    sources_cfg = news_cfg.get("sources", {})
    rss_cfg = sources_cfg.get("rss", {})
    if not rss_cfg.get("enabled", False):
        return []

    sources = []
    for feed in rss_cfg.get("feeds", []):
        sources.append(RSSSource(
            feed_name=feed["name"], feed_url=feed["url"],
            tier=feed.get("tier", 2), category=feed.get("category", ""),
        ))
    logger.info("Created %d RSS sources", len(sources))
    return sources
