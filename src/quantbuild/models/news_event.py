"""News event models for the XAUUSD news layer."""
from datetime import datetime
from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field


class SourceTier(IntEnum):
    """Source reliability tier. Lower = more authoritative."""
    TIER_1_PRIMARY = 1
    TIER_2_TRUSTED_MEDIA = 2
    TIER_3_SECONDARY = 3
    TIER_4_RUMOR = 4


class RawNewsItem(BaseModel):
    """Raw news item as received from a source, before normalization."""
    source_name: str
    headline: str
    body: Optional[str] = None
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    raw_data: Optional[dict] = None
    source_category: str = ""


class NormalizedNewsEvent(BaseModel):
    """Normalized news event — the single standard for all news in the pipeline."""
    event_id: str = Field(description="Unique event identifier (UUID)")
    received_at: datetime = Field(description="When bot received this event")
    published_at: Optional[datetime] = None

    source_name: str
    source_tier: SourceTier
    source_reliability_score: float = Field(ge=0.0, le=1.0)

    headline: str
    summary: Optional[str] = None
    raw_text: Optional[str] = None
    url: Optional[str] = None
    language: str = "en"

    topic_hints: list[str] = Field(default_factory=list)
    novelty_hint: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="0.0 = old news rehashed, 1.0 = completely new",
    )

    source_category: str = ""
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


class SentimentResult(BaseModel):
    """Result of sentiment analysis on a news event for XAUUSD."""
    event_id: str
    direction: str = Field(description="bullish / bearish / neutral for gold")
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = Field(description="rule_based / llm / hybrid")
    reasoning: str = ""
    impact_on_gold: float = Field(
        0.0, ge=-1.0, le=1.0,
        description="-1.0 = very bearish gold, +1.0 = very bullish gold",
    )


class GoldEventClassification(BaseModel):
    """Classification of a news event for its XAUUSD impact."""
    niche: str = "unknown"
    event_type: str = "unknown"
    impact_speed: str = "medium"
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    matched_keywords: list[str] = Field(default_factory=list)
