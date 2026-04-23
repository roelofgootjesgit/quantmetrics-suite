"""NewsAPI source via newsapi.org."""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.quantbuild.models.news_event import RawNewsItem, SourceTier
from src.quantbuild.news.base import NewsSource

logger = logging.getLogger(__name__)

_BASE_URL = "https://newsapi.org/v2"


class NewsAPISource(NewsSource):
    def __init__(self, api_key: str, categories: list[str] | None = None, language: str = "en"):
        self._api_key = api_key
        self._categories = categories or ["general"]
        self._language = language
        self._http = httpx.Client(base_url=_BASE_URL, timeout=15.0, headers={"X-Api-Key": api_key})

    @property
    def name(self) -> str:
        return "NewsAPI"

    @property
    def tier(self) -> SourceTier:
        return SourceTier.TIER_2_TRUSTED_MEDIA

    def fetch(self) -> list[RawNewsItem]:
        all_items: list[RawNewsItem] = []
        for category in self._categories:
            all_items.extend(self._fetch_category(category))
        return all_items

    def _fetch_category(self, category: str) -> list[RawNewsItem]:
        try:
            resp = self._http.get("/top-headlines", params={"category": category, "language": self._language, "pageSize": 20})
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.warning("NewsAPI: failed to fetch category %s", category)
            return []

        items: list[RawNewsItem] = []
        for article in data.get("articles", []):
            title = (article.get("title") or "").strip()
            if not title or title == "[Removed]":
                continue
            source_name = article.get("source", {}).get("name", "NewsAPI")
            published_at = None
            if pub_str := article.get("publishedAt"):
                try:
                    published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                except ValueError:
                    pass
            items.append(RawNewsItem(
                source_name=source_name, headline=title,
                body=article.get("description") or article.get("content"),
                url=article.get("url"), published_at=published_at,
                raw_data={"newsapi_source": source_name},
            ))
        return items

    def close(self) -> None:
        self._http.close()


def create_newsapi_source(cfg: dict[str, Any]) -> Optional[NewsAPISource]:
    news_cfg = cfg.get("news", {})
    sources_cfg = news_cfg.get("sources", {})
    api_cfg = sources_cfg.get("newsapi", {})
    if not api_cfg.get("enabled", False):
        return None
    api_key = news_cfg.get("newsapi_key", "")
    if not api_key:
        logger.warning("NewsAPI enabled but no API key configured")
        return None
    return NewsAPISource(api_key=api_key, categories=api_cfg.get("categories", ["general"]), language=api_cfg.get("language", "en"))
