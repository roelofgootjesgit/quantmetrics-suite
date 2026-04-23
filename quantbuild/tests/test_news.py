"""Unit tests for news layer modules."""
import pytest
from datetime import datetime, timezone, timedelta

from src.quantbuild.models.news_event import (
    SourceTier, RawNewsItem, NormalizedNewsEvent, SentimentResult, GoldEventClassification,
)
from src.quantbuild.news.normalizer import NewsNormalizer, _extract_topic_hints, _headline_hash
from src.quantbuild.news.relevance_filter import RelevanceFilter, RelevanceResult
from src.quantbuild.news.gold_classifier import GoldEventClassifier
from src.quantbuild.news.sentiment import RuleBasedSentiment
from src.quantbuild.news.advisor import LLMTradeAdvisor
from src.quantbuild.news.counter_news import CounterNewsDetector
from src.quantbuild.strategy_modules.news_gate import NewsGate
from src.quantbuild.models.trade import Position


def _make_event(headline: str, source: str = "Reuters", tier: int = 1,
                topics: list[str] | None = None) -> NormalizedNewsEvent:
    return NormalizedNewsEvent(
        event_id="test-001",
        received_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc),
        source_name=source,
        source_tier=SourceTier(tier),
        source_reliability_score=0.9,
        headline=headline,
        topic_hints=topics or [],
    )


class TestTopicExtraction:
    def test_gold_keywords(self):
        topics = _extract_topic_hints("Gold price surges to record high on Fed rate cut")
        assert "gold" in topics
        assert "central_banks" in topics

    def test_geopolitics(self):
        topics = _extract_topic_hints("War escalation sends markets into turmoil")
        assert "geopolitics" in topics

    def test_dollar(self):
        topics = _extract_topic_hints("DXY dollar index falls to 6-month low")
        assert "dollar" in topics

    def test_no_match(self):
        topics = _extract_topic_hints("New iPhone model announced")
        assert len(topics) == 0


class TestNormalizer:
    def test_basic_normalize(self):
        cfg = {"news": {"source_tiers": {}}}
        normalizer = NewsNormalizer(cfg)
        item = RawNewsItem(source_name="Test", headline="Gold rallies")
        event = normalizer.normalize(item, SourceTier.TIER_1_PRIMARY)
        assert event.headline == "Gold rallies"
        assert not event.is_duplicate

    def test_dedup(self):
        cfg = {"news": {"source_tiers": {}}}
        normalizer = NewsNormalizer(cfg)
        item = RawNewsItem(source_name="Test", headline="Same headline twice")
        e1 = normalizer.normalize(item, SourceTier.TIER_1_PRIMARY)
        e2 = normalizer.normalize(item, SourceTier.TIER_1_PRIMARY)
        assert not e1.is_duplicate
        assert e2.is_duplicate

    def test_headline_hash_case_insensitive(self):
        assert _headline_hash("Gold Surges") == _headline_hash("gold surges")


class TestRelevanceFilter:
    def test_gold_headline_passes(self):
        cfg = {"news": {"filter": {
            "min_relevance_score": 0.5,
            "max_age_minutes": 15,
            "gold_keywords": ["gold", "bullion"],
            "macro_keywords": ["fed"],
            "geopolitics_keywords": ["war"],
            "categories": ["gold", "macro"],
        }}}
        f = RelevanceFilter(cfg)
        event = _make_event("Gold price hits $3000 record", topics=["gold"])
        result = f.check(event)
        assert result.passed
        assert result.score > 0.5

    def test_irrelevant_headline_blocked(self):
        cfg = {"news": {"filter": {
            "min_relevance_score": 0.5,
            "max_age_minutes": 15,
            "gold_keywords": ["gold"],
            "macro_keywords": ["fed"],
            "geopolitics_keywords": ["war"],
            "categories": ["gold", "macro"],
        }}}
        f = RelevanceFilter(cfg)
        event = _make_event("New iPhone released", topics=[])
        event.published_at = datetime.now(timezone.utc) - timedelta(hours=2)
        result = f.check(event)
        assert not result.passed


class TestGoldClassifier:
    def test_rate_cut(self):
        classifier = GoldEventClassifier({})
        event = _make_event("Fed announces rate cut of 25 basis points")
        result = classifier.classify(event)
        assert result.niche == "macro"
        assert "rates" in result.event_type or "macro" in result.event_type

    def test_gold_direct(self):
        classifier = GoldEventClassifier({})
        event = _make_event("Gold price surges to all-time high on safe haven demand")
        result = classifier.classify(event)
        assert result.niche == "gold"

    def test_geopolitics(self):
        classifier = GoldEventClassifier({})
        event = _make_event("Military escalation in Middle East raises fears")
        result = classifier.classify(event)
        assert result.niche == "geopolitics"


class TestRuleBasedSentiment:
    def test_bullish_gold(self):
        engine = RuleBasedSentiment()
        event = _make_event("Fed signals rate cut, gold surges as dollar weakness continues")
        result = engine.analyze(event)
        assert result.direction == "bullish"
        assert result.impact_on_gold > 0

    def test_bearish_gold(self):
        engine = RuleBasedSentiment()
        event = _make_event("Strong jobs report, rate hike expected, dollar rallies")
        result = engine.analyze(event)
        assert result.direction == "bearish"
        assert result.impact_on_gold < 0

    def test_neutral(self):
        engine = RuleBasedSentiment()
        event = _make_event("New iPhone model announced by Apple")
        result = engine.analyze(event)
        assert result.direction == "neutral"


class TestNewsGate:
    def test_no_block_by_default(self):
        gate = NewsGate({"news": {"gate": {}, "sentiment": {}}})
        result = gate.check_gate(datetime.now(timezone.utc), "LONG")
        assert result["allowed"]

    def test_block_around_event(self):
        gate = NewsGate({"news": {"gate": {"block_minutes_before_high_impact": 30,
                                            "block_minutes_after_high_impact": 15,
                                            "high_impact_events": ["FOMC"]},
                                   "sentiment": {}}})
        event_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        gate.add_scheduled_event("FOMC", event_time)
        result = gate.check_gate(datetime.now(timezone.utc), "LONG")
        assert not result["allowed"]
        assert "FOMC" in result["reason"]

    def test_sentiment_boost(self):
        gate = NewsGate({"news": {"gate": {}, "sentiment": {"boost_threshold": 0.5, "suppress_threshold": 0.3}}})
        event = _make_event("Gold surges on rate cut", topics=["gold"])
        sentiment = SentimentResult(
            event_id=event.event_id, direction="bullish",
            confidence=0.8, method="rule_based", impact_on_gold=0.7,
        )
        gate.add_news_event(event, sentiment)
        result = gate.check_gate(datetime.now(timezone.utc), "LONG")
        assert result["allowed"]
        assert result["boost"] > 1.0


class TestCounterNews:
    def test_detect_contradiction(self):
        detector = CounterNewsDetector({"news": {"counter_news": {"exit_threshold": 0.8}}})
        event = _make_event("Gold crashes as dollar strengthens sharply", topics=["gold", "dollar"])
        position = Position(
            trade_id="T1", instrument="XAU_USD", direction="LONG",
            entry_price=2000.0, units=1.0, sl=1990.0, tp=2020.0,
            open_time=datetime.now(timezone.utc),
        )
        affected = detector.check_against_positions(event, [position])
        assert len(affected) > 0
        assert affected[0]["trade_id"] == "T1"


class TestLLMTradeAdvisor:
    def test_disabled_returns_neutral(self):
        advisor = LLMTradeAdvisor({"news": {"advisor": {"enabled": False}}, "ai": {}})
        result = advisor.evaluate(
            now=datetime.now(timezone.utc),
            direction="LONG",
            regime="trend",
            sentiment_summary={"avg_impact": 0.0, "event_count": 3},
            recent_events=[
                _make_event("Gold steady ahead of FOMC"),
                _make_event("Dollar index flat in quiet session"),
            ],
        )
        assert result["allowed"]
        assert result["risk_multiplier"] == 1.0
        assert result["stance"] == "neutral"

    def test_fallback_strong_counter_news_blocks(self):
        cfg = {
            "news": {"advisor": {"enabled": True, "min_events": 2, "block_on_strong_contra": True}},
            "ai": {"openai_api_key": ""},
        }
        advisor = LLMTradeAdvisor(cfg)
        now = datetime.now(timezone.utc)
        events = [
            _make_event("Dollar surges after hawkish Fed remarks"),
            _make_event("Gold drops as yields spike"),
        ]
        for e in events:
            e.received_at = now
        result = advisor.evaluate(
            now=now,
            direction="LONG",
            regime="trend",
            sentiment_summary={"avg_impact": -0.9, "event_count": 4},
            recent_events=events,
        )
        assert result["stance"] == "contra"
        assert not result["allowed"]
        assert result["risk_multiplier"] < 1.0
