"""News normalizer: Raw -> Normalized + dedup + topic extraction for XAUUSD."""
import hashlib
import logging
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from src.quantbuild.models.news_event import NormalizedNewsEvent, RawNewsItem, SourceTier

logger = logging.getLogger(__name__)

_DEFAULT_RELIABILITY = {
    SourceTier.TIER_1_PRIMARY: 0.95,
    SourceTier.TIER_2_TRUSTED_MEDIA: 0.80,
    SourceTier.TIER_3_SECONDARY: 0.55,
    SourceTier.TIER_4_RUMOR: 0.25,
}

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "gold": [
        "gold", "xauusd", "xau", "bullion", "precious metals", "gold price",
        "gold futures", "comex", "lbma", "gold etf", "gld", "gold mining",
    ],
    "commodities": [
        "silver", "platinum", "palladium", "copper", "oil", "crude",
        "commodity", "commodities", "mining",
    ],
    "macro": [
        "gdp", "inflation", "cpi", "ppi", "unemployment", "payroll", "jobs",
        "retail sales", "pmi", "housing", "consumer confidence", "recession",
    ],
    "central_banks": [
        "fed", "federal reserve", "fomc", "ecb", "boj", "interest rate",
        "rate cut", "rate hike", "hawkish", "dovish", "powell", "lagarde",
        "monetary policy", "quantitative", "tightening", "easing",
    ],
    "dollar": [
        "dxy", "dollar", "usd", "dollar index", "us dollar", "greenback",
        "treasury", "yield", "bond", "10-year", "real yield",
    ],
    "geopolitics": [
        "war", "sanction", "tariff", "conflict", "military", "invasion",
        "ceasefire", "nuclear", "crisis", "safe haven", "embargo", "nato",
    ],
    "risk_sentiment": [
        "vix", "risk", "fear", "panic", "sell-off", "rally", "stock market",
        "s&p", "nasdaq", "recession fears", "risk off", "risk on",
    ],
}


class NewsNormalizer:
    def __init__(self, cfg: dict[str, Any]):
        news_cfg = cfg.get("news", {})
        tier_cfg = news_cfg.get("source_tiers", {})
        self._reliability: dict[SourceTier, float] = {
            SourceTier.TIER_1_PRIMARY: tier_cfg.get("tier_1_reliability", 0.95),
            SourceTier.TIER_2_TRUSTED_MEDIA: tier_cfg.get("tier_2_reliability", 0.80),
            SourceTier.TIER_3_SECONDARY: tier_cfg.get("tier_3_reliability", 0.55),
            SourceTier.TIER_4_RUMOR: tier_cfg.get("tier_4_reliability", 0.25),
        }
        self._seen: OrderedDict[str, str] = OrderedDict()
        self._max_seen = 5000

    def normalize(self, item: RawNewsItem, source_tier: SourceTier) -> NormalizedNewsEvent:
        event_id = str(uuid.uuid4())
        dedup_hash = _headline_hash(item.headline)
        is_dup = dedup_hash in self._seen
        dup_of = self._seen.get(dedup_hash)

        if not is_dup:
            self._seen[dedup_hash] = event_id
            if len(self._seen) > self._max_seen:
                self._seen.popitem(last=False)

        return NormalizedNewsEvent(
            event_id=event_id,
            received_at=datetime.now(timezone.utc),
            published_at=item.published_at,
            source_name=item.source_name,
            source_tier=source_tier,
            source_reliability_score=self._reliability.get(source_tier, 0.5),
            headline=item.headline,
            summary=item.body, raw_text=item.body,
            url=item.url,
            topic_hints=_extract_topic_hints(item.headline),
            source_category=item.source_category,
            is_duplicate=is_dup, duplicate_of=dup_of,
        )

    def normalize_batch(self, items: list[RawNewsItem], source_tier: SourceTier) -> list[NormalizedNewsEvent]:
        return [self.normalize(item, source_tier) for item in items]

    def reset_seen(self) -> None:
        self._seen.clear()

    @property
    def seen_count(self) -> int:
        return len(self._seen)


def _headline_hash(headline: str) -> str:
    return hashlib.md5(headline.lower().strip().encode("utf-8")).hexdigest()[:16]


def _extract_topic_hints(headline: str) -> list[str]:
    lower = headline.lower()
    return [topic for topic, keywords in _TOPIC_KEYWORDS.items() if any(kw in lower for kw in keywords)]
