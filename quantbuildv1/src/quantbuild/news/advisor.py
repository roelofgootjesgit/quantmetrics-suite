"""LLM-assisted trade advisor for final news-aware execution checks."""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.quantbuild.models.news_event import NormalizedNewsEvent

logger = logging.getLogger(__name__)


class LLMTradeAdvisor:
    """Optional advisory layer that can block/suppress/boost a trade idea."""

    def __init__(self, cfg: dict[str, Any]):
        news_cfg = cfg.get("news", {})
        advisor_cfg = news_cfg.get("advisor", {})
        ai_cfg = cfg.get("ai", {})

        self._enabled = bool(advisor_cfg.get("enabled", False))
        self._model = str(advisor_cfg.get("model") or ai_cfg.get("model", "gpt-4o-mini"))
        self._api_key = str(ai_cfg.get("openai_api_key", "")).strip()
        self._min_events = int(advisor_cfg.get("min_events", 2))
        self._recent_window_minutes = int(advisor_cfg.get("recent_window_minutes", 45))
        self._max_headlines = int(advisor_cfg.get("max_headlines", 8))
        self._block_on_strong_contra = bool(advisor_cfg.get("block_on_strong_contra", True))
        self._block_confidence = float(advisor_cfg.get("block_confidence", 0.75))
        self._cache_ttl_seconds = int(advisor_cfg.get("cache_ttl_seconds", 120))
        self._fallback_strong_impact = float(advisor_cfg.get("fallback_strong_impact", 0.65))

        self._client = None
        self._last_result_key: Optional[str] = None
        self._last_result_expires_at: Optional[datetime] = None
        self._last_result_payload: Optional[dict[str, Any]] = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def available(self) -> bool:
        if not self._enabled:
            return False
        if not self._api_key:
            return False
        try:
            import openai  # noqa: F401

            return True
        except ImportError:
            return False

    def _ensure_client(self) -> None:
        if self._client is None:
            import openai

            self._client = openai.OpenAI(api_key=self._api_key)

    def evaluate(
        self,
        *,
        now: datetime,
        direction: str,
        regime: Optional[str],
        sentiment_summary: Optional[dict[str, Any]],
        recent_events: list[NormalizedNewsEvent],
    ) -> dict[str, Any]:
        """Return trade advice with allow/block and risk multiplier."""
        if not self._enabled:
            return self._neutral("disabled")

        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        window_start = now - timedelta(minutes=self._recent_window_minutes)
        scoped_events = []
        for evt in recent_events:
            ts = evt.received_at if evt.received_at.tzinfo else evt.received_at.replace(tzinfo=timezone.utc)
            if ts >= window_start:
                scoped_events.append(evt)
        scoped_events = scoped_events[-self._max_headlines :]

        event_count = len(scoped_events)
        if event_count < self._min_events:
            return self._neutral("insufficient_recent_events")

        summary = sentiment_summary or {}
        avg_impact = float(summary.get("avg_impact", 0.0) or 0.0)
        summary_count = int(summary.get("event_count", event_count) or event_count)

        cache_key = f"{direction}|{regime}|{round(avg_impact, 3)}|{summary_count}|{event_count}"
        if self._cache_valid(cache_key, now):
            return dict(self._last_result_payload or self._neutral("cache_miss"))

        if self.available:
            try:
                result = self._evaluate_llm(
                    direction=direction,
                    regime=regime,
                    avg_impact=avg_impact,
                    summary_count=summary_count,
                    events=scoped_events,
                )
                self._set_cache(cache_key, now, result)
                return result
            except Exception as e:
                logger.warning("LLM trade advisor failed, fallback active: %s", str(e)[:120])

        fallback = self._evaluate_fallback(
            direction=direction,
            avg_impact=avg_impact,
            summary_count=summary_count,
        )
        self._set_cache(cache_key, now, fallback)
        return fallback

    def _evaluate_llm(
        self,
        *,
        direction: str,
        regime: Optional[str],
        avg_impact: float,
        summary_count: int,
        events: list[NormalizedNewsEvent],
    ) -> dict[str, Any]:
        self._ensure_client()
        compact_events = [
            {
                "source": e.source_name,
                "tier": int(e.source_tier),
                "headline": e.headline[:180],
                "topics": e.topic_hints[:4],
            }
            for e in events
        ]
        system = (
            "You are an execution advisor for an XAUUSD trading system. "
            "Given current trade direction and recent filtered news, return strict JSON only with keys: "
            '{"stance":"align|contra|neutral","confidence":0..1,"risk_multiplier":0.5..1.3,'
            '"allow_trade":true|false,"reason":"short"}'
        )
        user_payload = {
            "direction": direction,
            "regime": regime or "unknown",
            "avg_impact": avg_impact,
            "sentiment_event_count": summary_count,
            "events": compact_events,
        }

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
            temperature=0.1,
            max_tokens=220,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        stance = str(data.get("stance", "neutral")).lower().strip()
        confidence = min(max(float(data.get("confidence", 0.5)), 0.0), 1.0)
        risk_multiplier = min(max(float(data.get("risk_multiplier", 1.0)), 0.5), 1.3)
        allow_trade = bool(data.get("allow_trade", True))
        reason = str(data.get("reason", "llm_advisor"))

        if self._block_on_strong_contra and stance == "contra" and confidence >= self._block_confidence:
            allow_trade = False
            reason = f"llm_strong_contra: {reason}"

        return {
            "allowed": allow_trade,
            "risk_multiplier": risk_multiplier,
            "method": "llm_advisor",
            "stance": stance,
            "confidence": confidence,
            "reason": reason,
        }

    def _evaluate_fallback(self, *, direction: str, avg_impact: float, summary_count: int) -> dict[str, Any]:
        # Heuristic fallback keeps behaviour deterministic when LLM is unavailable.
        contra = (direction == "LONG" and avg_impact < 0) or (direction == "SHORT" and avg_impact > 0)
        magnitude = abs(avg_impact)
        if contra and summary_count >= self._min_events and magnitude >= self._fallback_strong_impact:
            allowed = not self._block_on_strong_contra
            return {
                "allowed": allowed,
                "risk_multiplier": 0.65,
                "method": "heuristic_fallback",
                "stance": "contra",
                "confidence": min(0.9, 0.45 + magnitude),
                "reason": "fallback_strong_counter_news",
            }

        if contra and summary_count >= self._min_events:
            return {
                "allowed": True,
                "risk_multiplier": 0.85,
                "method": "heuristic_fallback",
                "stance": "contra",
                "confidence": min(0.8, 0.35 + magnitude),
                "reason": "fallback_mild_counter_news",
            }

        return self._neutral("fallback_neutral")

    def _neutral(self, reason: str) -> dict[str, Any]:
        return {
            "allowed": True,
            "risk_multiplier": 1.0,
            "method": "neutral",
            "stance": "neutral",
            "confidence": 0.0,
            "reason": reason,
        }

    def _cache_valid(self, key: str, now: datetime) -> bool:
        if self._last_result_key != key:
            return False
        if self._last_result_expires_at is None:
            return False
        if self._last_result_payload is None:
            return False
        return now <= self._last_result_expires_at

    def _set_cache(self, key: str, now: datetime, result: dict[str, Any]) -> None:
        self._last_result_key = key
        self._last_result_expires_at = now + timedelta(seconds=self._cache_ttl_seconds)
        self._last_result_payload = dict(result)
