"""Unit tests for Pydantic models."""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.quantbuild.models.trade import Trade, TradeDirection, TradeResult, Position, calculate_rr
from src.quantbuild.models.signal import Signal, SignalStrength, EntryCandidate
from src.quantbuild.models.news_event import (
    SourceTier, RawNewsItem, NormalizedNewsEvent, SentimentResult, GoldEventClassification,
)
from src.quantbuild.models.config_schema import BacktestConfig, RiskConfig, StrategyConfig, AppConfig


class TestTradeModel:
    def test_create_valid(self):
        t = Trade(
            timestamp_open=datetime(2025, 1, 1, 10, 0),
            timestamp_close=datetime(2025, 1, 1, 11, 0),
            symbol="XAUUSD", direction=TradeDirection.LONG,
            entry_price=2000.0, exit_price=2004.0, sl=1998.0, tp=2004.0,
            profit_usd=4.0, profit_r=2.0, result=TradeResult.WIN,
        )
        assert t.direction == TradeDirection.LONG
        assert t.result == TradeResult.WIN

    def test_optional_fields(self):
        t = Trade(
            timestamp_open=datetime(2025, 1, 1), timestamp_close=datetime(2025, 1, 1),
            symbol="XAUUSD", direction="LONG",
            entry_price=2000.0, exit_price=2004.0, sl=1998.0, tp=2004.0,
            profit_usd=4.0, profit_r=2.0, result="WIN",
        )
        assert t.regime is None
        assert t.news_sentiment_at_entry is None


class TestSignalModel:
    def test_create(self):
        s = Signal(timestamp=datetime.now(), direction="LONG", modules_fired=["liquidity_sweep"])
        assert s.strength == SignalStrength.MODERATE
        assert s.news_boost == 1.0

    def test_entry_candidate_blocked(self):
        s = Signal(timestamp=datetime.now(), direction="LONG")
        ec = EntryCandidate(signal=s, atr=5.0, tp_price=2010.0, sl_price=1995.0, blocked_reason="news_gate")
        assert not ec.is_allowed

    def test_entry_candidate_allowed(self):
        s = Signal(timestamp=datetime.now(), direction="SHORT")
        ec = EntryCandidate(signal=s, atr=5.0, tp_price=1990.0, sl_price=2005.0)
        assert ec.is_allowed


class TestNewsEventModels:
    def test_raw_news_item(self):
        item = RawNewsItem(source_name="Kitco", headline="Gold surges")
        assert item.body is None

    def test_normalized_event(self):
        event = NormalizedNewsEvent(
            event_id="abc-123", received_at=datetime.now(timezone.utc),
            source_name="Reuters", source_tier=SourceTier.TIER_1_PRIMARY,
            source_reliability_score=0.95, headline="Fed cuts rates by 25bps",
            topic_hints=["central_banks", "macro"],
        )
        assert event.source_tier == 1
        assert not event.is_duplicate

    def test_sentiment_result(self):
        sr = SentimentResult(event_id="x", direction="bullish", confidence=0.85, method="llm", impact_on_gold=0.7)
        assert sr.impact_on_gold > 0

    def test_gold_classification(self):
        gc = GoldEventClassification(niche="macro", event_type="macro_rates", impact_speed="fast", confidence=0.9)
        assert gc.niche == "macro"


class TestConfigSchema:
    def test_backtest_defaults(self):
        bc = BacktestConfig()
        assert bc.tp_r == 2.0

    def test_backtest_validation(self):
        with pytest.raises(ValidationError):
            BacktestConfig(tp_r=0.1)

    def test_app_config_defaults(self):
        ac = AppConfig()
        assert ac.symbol == "XAUUSD"
        assert ac.news.enabled is False

    def test_strategy_config(self):
        sc = StrategyConfig()
        assert sc.require_structure is True
        assert sc.liquidity_sweep.lookback_candles == 20


class TestCalculateRR:
    def test_long_win(self):
        assert calculate_rr(2000, 2004, 1998, "LONG") == pytest.approx(2.0)

    def test_long_loss(self):
        assert calculate_rr(2000, 1998, 1998, "LONG") == pytest.approx(-1.0)

    def test_short_win(self):
        assert calculate_rr(2000, 1996, 2002, "SHORT") == pytest.approx(2.0)

    def test_zero_risk(self):
        assert calculate_rr(2000, 2000, 2000, "LONG") == 0.0
