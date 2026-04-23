"""XAUUSD sentiment engine: rule-based + LLM hybrid for gold impact analysis."""
import logging
from typing import Any, Optional

from src.quantbuild.models.news_event import NormalizedNewsEvent, SentimentResult

logger = logging.getLogger(__name__)

_BULLISH_GOLD_KEYWORDS = [
    "rate cut", "dovish", "easing", "inflation rises", "cpi higher",
    "gold surges", "gold rallies", "safe haven demand", "geopolitical risk",
    "war", "conflict", "sanctions", "dollar weakness", "dollar falls",
    "dxy falls", "recession fears", "risk off", "debt ceiling",
    "gold demand", "central bank buying", "flight to safety",
    "negative real yields", "stimulus", "quantitative easing",
]

_BEARISH_GOLD_KEYWORDS = [
    "rate hike", "hawkish", "tightening", "inflation falls", "cpi lower",
    "gold falls", "gold drops", "gold sells off",
    "dollar strength", "dollar rallies", "dxy rises",
    "strong jobs", "nfp beats", "employment strong",
    "risk on", "stock rally", "equity rally",
    "tapering", "quantitative tightening", "higher for longer",
]


class RuleBasedSentiment:
    """Rule-based gold sentiment using keyword matching."""

    def analyze(self, event: NormalizedNewsEvent) -> SentimentResult:
        text = (event.headline + " " + (event.summary or "")).lower()

        bull_hits = sum(1 for kw in _BULLISH_GOLD_KEYWORDS if kw in text)
        bear_hits = sum(1 for kw in _BEARISH_GOLD_KEYWORDS if kw in text)

        total = bull_hits + bear_hits
        if total == 0:
            return SentimentResult(
                event_id=event.event_id, direction="neutral",
                confidence=0.1, method="rule_based",
                reasoning="No gold-relevant keywords found",
                impact_on_gold=0.0,
            )

        if bull_hits > bear_hits:
            confidence = min(bull_hits / max(total, 1) * 0.8, 0.9)
            impact = min(bull_hits * 0.15, 0.9)
            return SentimentResult(
                event_id=event.event_id, direction="bullish",
                confidence=confidence, method="rule_based",
                reasoning=f"Bullish keywords: {bull_hits} vs bearish: {bear_hits}",
                impact_on_gold=impact,
            )
        elif bear_hits > bull_hits:
            confidence = min(bear_hits / max(total, 1) * 0.8, 0.9)
            impact = -min(bear_hits * 0.15, 0.9)
            return SentimentResult(
                event_id=event.event_id, direction="bearish",
                confidence=confidence, method="rule_based",
                reasoning=f"Bearish keywords: {bear_hits} vs bullish: {bull_hits}",
                impact_on_gold=impact,
            )
        else:
            return SentimentResult(
                event_id=event.event_id, direction="neutral",
                confidence=0.3, method="rule_based",
                reasoning=f"Mixed signals: {bull_hits} bullish, {bear_hits} bearish",
                impact_on_gold=0.0,
            )


class LLMSentiment:
    """LLM-based gold sentiment via OpenAI."""

    def __init__(self, cfg: dict[str, Any]):
        ai_cfg = cfg.get("ai", {})
        self._model = ai_cfg.get("model", "gpt-4o-mini")
        self._api_key = ai_cfg.get("openai_api_key", "")
        self._client = None

    @property
    def available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import openai
            return True
        except ImportError:
            return False

    def _ensure_client(self):
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self._api_key)

    def analyze(self, event: NormalizedNewsEvent) -> SentimentResult:
        self._ensure_client()
        system = (
            "You are a gold (XAUUSD) market analyst. Given a news headline, "
            "determine its likely impact on gold price. Respond in JSON with: "
            '{"direction": "bullish"|"bearish"|"neutral", "confidence": 0.0-1.0, '
            '"impact": -1.0 to 1.0, "reasoning": "brief explanation"}'
        )
        user = f"Headline: {event.headline}\nSource: {event.source_name} (tier {event.source_tier})"
        if event.summary:
            user += f"\nSummary: {event.summary[:300]}"

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=200, temperature=0.2,
                response_format={"type": "json_object"},
            )
            import json
            data = json.loads(response.choices[0].message.content)
            return SentimentResult(
                event_id=event.event_id,
                direction=data.get("direction", "neutral"),
                confidence=min(max(float(data.get("confidence", 0.5)), 0), 1),
                method="llm",
                reasoning=data.get("reasoning", "LLM analysis"),
                impact_on_gold=min(max(float(data.get("impact", 0)), -1), 1),
            )
        except Exception as e:
            logger.warning("LLM sentiment failed: %s", str(e)[:100])
            raise


class HybridSentiment:
    """Hybrid engine: tries LLM, falls back to rule-based."""

    def __init__(self, cfg: dict[str, Any]):
        self._mode = cfg.get("news", {}).get("sentiment", {}).get("mode", "rule_based")
        self._rule_engine = RuleBasedSentiment()
        self._llm_engine: Optional[LLMSentiment] = None
        if self._mode in ("llm", "hybrid"):
            self._llm_engine = LLMSentiment(cfg)

    def analyze(self, event: NormalizedNewsEvent) -> SentimentResult:
        if self._mode == "rule_based" or not self._llm_engine:
            return self._rule_engine.analyze(event)

        if self._mode == "llm":
            if self._llm_engine.available:
                return self._llm_engine.analyze(event)
            return self._rule_engine.analyze(event)

        # hybrid: try LLM, fallback to rules
        if self._llm_engine.available:
            try:
                return self._llm_engine.analyze(event)
            except Exception:
                logger.info("LLM failed, using rule-based fallback")
        return self._rule_engine.analyze(event)

    @property
    def method(self) -> str:
        return self._mode
