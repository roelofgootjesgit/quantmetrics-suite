"""Pydantic-based typed models for the trading system."""
from src.quantbuild.models.trade import Trade, TradeResult, TradeDirection, Position, calculate_rr
from src.quantbuild.models.signal import Signal, SignalStrength, EntryCandidate
from src.quantbuild.models.news_event import (
    SourceTier,
    RawNewsItem,
    NormalizedNewsEvent,
    SentimentResult,
    GoldEventClassification,
)
from src.quantbuild.models.config_schema import (
    BacktestConfig,
    RiskConfig,
    StrategyConfig,
    NewsConfig,
    BrokerConfig,
    AppConfig,
)

__all__ = [
    "Trade", "TradeResult", "TradeDirection", "Position", "calculate_rr",
    "Signal", "SignalStrength", "EntryCandidate",
    "SourceTier", "RawNewsItem", "NormalizedNewsEvent", "SentimentResult", "GoldEventClassification",
    "BacktestConfig", "RiskConfig", "StrategyConfig", "NewsConfig", "BrokerConfig", "AppConfig",
]
