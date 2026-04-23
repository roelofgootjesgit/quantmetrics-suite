"""Relevance filter for XAUUSD — determines if news is worth processing."""
import logging
from datetime import datetime, timezone
from typing import Any

from src.quantbuild.models.news_event import NormalizedNewsEvent

logger = logging.getLogger(__name__)


class RelevanceResult:
    __slots__ = ("passed", "score", "semantic_score", "time_score", "reasons")
    def __init__(self):
        self.passed: bool = False
        self.score: float = 0.0
        self.semantic_score: float = 0.0
        self.time_score: float = 0.0
        self.reasons: list[str] = []


class RelevanceFilter:
    def __init__(self, cfg: dict[str, Any]):
        filter_cfg = cfg.get("news", {}).get("filter", {})
        self.min_score: float = filter_cfg.get("min_relevance_score", 0.5)
        self.max_age_minutes: int = filter_cfg.get("max_age_minutes", 15)
        self.categories: list[str] = filter_cfg.get("categories", [])
        self.gold_keywords: list[str] = [k.lower() for k in filter_cfg.get("gold_keywords", ["gold", "xauusd", "bullion"])]
        self.macro_keywords: list[str] = [k.lower() for k in filter_cfg.get("macro_keywords", ["fed", "inflation", "rate"])]
        self.geo_keywords: list[str] = [k.lower() for k in filter_cfg.get("geopolitics_keywords", ["war", "sanction", "conflict"])]
        self.whitelist: list[str] = [k.lower() for k in filter_cfg.get("keywords_whitelist", [])]
        self.blacklist: list[str] = [k.lower() for k in filter_cfg.get("keywords_blacklist", [])]

    def check(self, event: NormalizedNewsEvent) -> RelevanceResult:
        result = RelevanceResult()
        if event.is_duplicate:
            result.reasons.append("duplicate")
            return result

        result.semantic_score = self._semantic_score(event)
        result.time_score = self._time_score(event)
        result.score = (result.semantic_score * 0.7) + (result.time_score * 0.3)
        result.passed = result.score >= self.min_score
        if not result.passed:
            result.reasons.append(f"score {result.score:.2f} < {self.min_score:.2f}")
        return result

    def filter_batch(self, events: list[NormalizedNewsEvent]) -> list[NormalizedNewsEvent]:
        passed = [e for e in events if self.check(e).passed]
        logger.info("Relevance filter: %d/%d events passed", len(passed), len(events))
        return passed

    def _semantic_score(self, event: NormalizedNewsEvent) -> float:
        headline_lower = event.headline.lower()

        if any(kw in headline_lower for kw in self.blacklist):
            return 0.0

        if self.whitelist and any(kw in headline_lower for kw in self.whitelist):
            return 1.0

        score = 0.0

        # Direct gold mentions get highest score
        if any(kw in headline_lower for kw in self.gold_keywords):
            score = max(score, 0.95)

        # Macro/central bank news is highly relevant to gold
        if any(kw in headline_lower for kw in self.macro_keywords):
            score = max(score, 0.8)

        # Geopolitical news (safe haven demand)
        if any(kw in headline_lower for kw in self.geo_keywords):
            score = max(score, 0.7)

        # Topic-based scoring
        if event.topic_hints and self.categories:
            overlap = set(event.topic_hints) & set(self.categories)
            if overlap:
                topic_score = min(len(overlap) * 0.3 + 0.3, 0.9)
                score = max(score, topic_score)

        if score == 0.0 and event.topic_hints:
            score = 0.2

        tier_boost = max(0, (5 - event.source_tier)) * 0.03
        return min(score + tier_boost, 1.0)

    def _time_score(self, event: NormalizedNewsEvent) -> float:
        if not event.published_at:
            return 0.5
        now = datetime.now(timezone.utc)
        pub = event.published_at
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        age_minutes = (now - pub).total_seconds() / 60
        if age_minutes <= 0:
            return 1.0
        if age_minutes >= self.max_age_minutes:
            return 0.0
        return 1.0 - (age_minutes / self.max_age_minutes)
