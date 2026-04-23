"""Counter-news detector for gold positions — checks if new headlines contradict open thesis."""
import logging
from typing import Any

from src.quantbuild.models.news_event import NormalizedNewsEvent
from src.quantbuild.models.trade import Position

logger = logging.getLogger(__name__)

_CONTRADICTION_PAIRS = [
    ({"surge", "rally", "rise", "jump", "soar", "gain", "higher", "bullish", "up"},
     {"fall", "crash", "drop", "decline", "plunge", "lower", "bearish", "down", "sell"}),
    ({"cut", "dovish", "easing", "stimulus", "weaken"},
     {"hike", "hawkish", "tightening", "tapering", "strengthen"}),
    ({"war", "conflict", "escalation", "crisis", "risk"},
     {"peace", "ceasefire", "de-escalation", "agreement", "deal"}),
]


class CounterNewsDetector:
    def __init__(self, cfg: dict[str, Any]):
        counter_cfg = cfg.get("news", {}).get("counter_news", {})
        self._exit_threshold = counter_cfg.get("exit_threshold", 0.8)
        self._min_source_tier = 3

    def check_against_positions(
        self, event: NormalizedNewsEvent, positions: list[Position],
    ) -> list[dict]:
        """Returns list of affected positions with action recommendations."""
        affected = []
        for pos in positions:
            if not pos.thesis_valid:
                continue

            if not self._is_gold_related(event):
                continue

            contradiction_score = self._detect_contradiction(event, pos)
            if contradiction_score <= 0:
                continue

            source_authoritative = event.source_tier.value <= self._min_source_tier

            action = "exit" if (source_authoritative and contradiction_score >= self._exit_threshold) else "warn"

            affected.append({
                "trade_id": pos.trade_id,
                "direction": pos.direction,
                "contradiction_score": contradiction_score,
                "action": action,
                "reason": f"Counter-news from {event.source_name}: {event.headline[:80]}",
            })

            if action == "exit":
                logger.warning("THESIS INVALIDATED: %s by '%s'", pos.trade_id, event.headline[:60])
            else:
                logger.info("THESIS WEAKENED: %s by '%s'", pos.trade_id, event.headline[:60])

        return affected

    def _is_gold_related(self, event: NormalizedNewsEvent) -> bool:
        gold_topics = {"gold", "commodities", "macro", "central_banks", "dollar", "geopolitics"}
        if set(event.topic_hints) & gold_topics:
            return True
        lower = event.headline.lower()
        return any(kw in lower for kw in ["gold", "xau", "bullion", "fed", "rate", "dollar", "dxy"])

    def _detect_contradiction(self, event: NormalizedNewsEvent, position: Position) -> float:
        headline_lower = event.headline.lower()
        event_direction = self._get_gold_direction(headline_lower)
        if event_direction == "neutral":
            return 0.0

        pos_direction = "bullish" if position.direction == "LONG" else "bearish"

        if event_direction != pos_direction:
            base_score = 0.5
            if event.source_tier.value <= 2:
                base_score += 0.3
            return min(base_score, 1.0)
        return 0.0

    def _get_gold_direction(self, text: str) -> str:
        bull_hits = 0
        bear_hits = 0
        for bull_set, bear_set in _CONTRADICTION_PAIRS:
            for word in bull_set:
                if word in text:
                    bull_hits += 1
            for word in bear_set:
                if word in text:
                    bear_hits += 1
        if bull_hits > bear_hits:
            return "bullish"
        if bear_hits > bull_hits:
            return "bearish"
        return "neutral"
