"""Gold-specific event classifier — classifies news by XAUUSD impact."""
import logging
from typing import Any

from src.quantbuild.models.news_event import NormalizedNewsEvent, GoldEventClassification

logger = logging.getLogger(__name__)

_GOLD_PATTERNS: dict[str, tuple[list[str], str]] = {
    "gold_direct": (
        ["gold price", "gold futures", "xauusd", "xau", "bullion", "comex gold",
         "gold etf", "gld", "gold demand", "gold supply", "central bank gold",
         "gold reserves", "gold mining", "gold production"],
        "fast",
    ),
    "gold_safe_haven": (
        ["safe haven", "flight to safety", "risk aversion", "market panic",
         "geopolitical risk", "uncertainty", "gold as hedge"],
        "fast",
    ),
}

_MACRO_PATTERNS: dict[str, tuple[list[str], str]] = {
    "macro_rates": (
        ["rate cut", "rate hike", "interest rate", "fomc", "fed meeting",
         "basis points", "hawkish", "dovish", "tightening", "easing",
         "federal reserve", "ecb", "boj", "fed funds", "monetary policy"],
        "medium",
    ),
    "macro_inflation": (
        ["inflation", "cpi", "ppi", "consumer prices", "producer prices",
         "core inflation", "pce", "deflation", "disinflation", "stagflation"],
        "medium",
    ),
    "macro_employment": (
        ["nfp", "non-farm", "payroll", "unemployment", "jobs report",
         "jobless claims", "employment", "labor market", "hiring"],
        "medium",
    ),
    "macro_growth": (
        ["gdp", "recession", "economic growth", "retail sales", "pmi",
         "manufacturing", "services", "consumer confidence", "durable goods"],
        "medium",
    ),
    "macro_speech": (
        ["powell", "fed chair", "lagarde", "yellen", "testimony",
         "press conference", "jackson hole", "fed speak", "remarks"],
        "medium",
    ),
    "macro_fiscal": (
        ["debt ceiling", "fiscal", "stimulus", "spending", "budget",
         "treasury", "deficit", "government shutdown", "tariff", "trade war"],
        "slow",
    ),
}

_DOLLAR_PATTERNS: dict[str, tuple[list[str], str]] = {
    "dollar_strength": (
        ["dxy", "dollar index", "us dollar", "greenback", "dollar rally",
         "dollar strength", "dollar weakness", "dollar falls", "dollar rises"],
        "fast",
    ),
    "dollar_yields": (
        ["treasury yield", "10-year", "bond yield", "real yield", "yield curve",
         "bond auction", "treasury auction"],
        "medium",
    ),
}

_GEOPOLITICS_PATTERNS: dict[str, tuple[list[str], str]] = {
    "geo_conflict": (
        ["war", "invasion", "military", "attack", "bombing", "missile",
         "escalation", "ceasefire", "troops", "offensive"],
        "fast",
    ),
    "geo_sanctions": (
        ["sanction", "embargo", "tariff", "trade ban", "export controls",
         "economic sanctions", "frozen assets"],
        "medium",
    ),
    "geo_diplomacy": (
        ["peace talks", "negotiations", "treaty", "summit", "diplomacy",
         "de-escalation", "agreement", "deal"],
        "slow",
    ),
}

ALL_PATTERNS: dict[str, dict[str, tuple[list[str], str]]] = {
    "gold": _GOLD_PATTERNS,
    "macro": _MACRO_PATTERNS,
    "dollar": _DOLLAR_PATTERNS,
    "geopolitics": _GEOPOLITICS_PATTERNS,
}


class GoldEventClassifier:
    def __init__(self, cfg: dict[str, Any]):
        self._default_niche = "macro"

    def classify(self, event: NormalizedNewsEvent) -> GoldEventClassification:
        headline_lower = event.headline.lower()
        body_lower = (event.summary or "").lower()
        text = headline_lower + " " + body_lower

        best_niche = None
        best_type = None
        best_speed = "medium"
        best_score = 0
        matched_kw: list[str] = []

        for niche, patterns in ALL_PATTERNS.items():
            for event_type, (keywords, speed) in patterns.items():
                hits = [kw for kw in keywords if kw in text]
                score = len(hits)
                if "gold" in niche:
                    score *= 3
                elif niche != "macro":
                    score *= 2

                if score > best_score:
                    best_score = score
                    best_niche = niche
                    best_type = event_type
                    best_speed = speed
                    matched_kw = hits

        if best_niche and best_score > 0:
            return GoldEventClassification(
                niche=best_niche, event_type=best_type, impact_speed=best_speed,
                confidence=min(best_score / 6.0, 1.0), matched_keywords=matched_kw,
            )

        if event.topic_hints:
            for hint in event.topic_hints:
                if hint in ALL_PATTERNS:
                    return GoldEventClassification(
                        niche=hint, event_type=f"{hint}_general",
                        confidence=0.2, matched_keywords=[],
                    )

        return GoldEventClassification(
            niche=self._default_niche, event_type="unclassified",
            confidence=0.1, matched_keywords=[],
        )
