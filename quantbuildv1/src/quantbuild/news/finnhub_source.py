"""Finnhub source for market-focused headlines."""
import logging
from datetime import datetime
from typing import Any, Optional

import httpx

from src.quantbuild.models.news_event import RawNewsItem, SourceTier
from src.quantbuild.news.base import NewsSource

logger = logging.getLogger(__name__)

_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubSource(NewsSource):
    def __init__(self, api_key: str, category: str = "general", min_tier: int = 2):
        self._api_key = api_key
        self._category = category
        self._tier = SourceTier(min_tier)
        self._http = httpx.Client(base_url=_BASE_URL, timeout=12.0)

    @property
    def name(self) -> str:
        return "Finnhub"

    @property
    def tier(self) -> SourceTier:
        return self._tier

    def fetch(self) -> list[RawNewsItem]:
        try:
            resp = self._http.get(
                "/news",
                params={"category": self._category, "token": self._api_key},
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            logger.warning("Finnhub: fetch failed")
            return []

        items: list[RawNewsItem] = []
        for entry in payload if isinstance(payload, list) else []:
            headline = (entry.get("headline") or "").strip()
            if not headline:
                continue
            source_name = (entry.get("source") or "Finnhub").strip()
            summary = (entry.get("summary") or "").strip() or None
            url = (entry.get("url") or "").strip() or None
            published_at = _parse_unix_ts(entry.get("datetime"))

            items.append(
                RawNewsItem(
                    source_name=source_name,
                    headline=headline,
                    body=summary,
                    url=url,
                    published_at=published_at,
                    source_category=self._category,
                    raw_data={"finnhub_category": self._category},
                )
            )
        return items

    def close(self) -> None:
        self._http.close()


def _parse_unix_ts(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.utcfromtimestamp(int(ts))
    except Exception:
        return None


def create_finnhub_source(cfg: dict[str, Any]) -> Optional[FinnhubSource]:
    news_cfg = cfg.get("news", {})
    sources_cfg = news_cfg.get("sources", {})
    finnhub_cfg = sources_cfg.get("finnhub", {})
    if not finnhub_cfg.get("enabled", False):
        return None

    api_key = str(news_cfg.get("finnhub_api_key", "")).strip()
    if not api_key:
        logger.warning("Finnhub enabled but no API key configured")
        return None

    return FinnhubSource(
        api_key=api_key,
        category=finnhub_cfg.get("category", "general"),
        min_tier=int(finnhub_cfg.get("tier", 2)),
    )
