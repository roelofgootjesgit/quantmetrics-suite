"""Structure labels: BULLISH_STRUCTURE, BEARISH_STRUCTURE, RANGE."""
from typing import Literal

StructureLabel = Literal["BULLISH_STRUCTURE", "BEARISH_STRUCTURE", "RANGE"]

BULLISH_STRUCTURE: StructureLabel = "BULLISH_STRUCTURE"
BEARISH_STRUCTURE: StructureLabel = "BEARISH_STRUCTURE"
RANGE: StructureLabel = "RANGE"

ALL_LABELS: tuple[StructureLabel, ...] = (BULLISH_STRUCTURE, BEARISH_STRUCTURE, RANGE)


def no_trade_for_structure(label: StructureLabel) -> bool:
    return label == RANGE


def direction_allowed_for_structure(label: StructureLabel, direction: str) -> bool:
    if label == RANGE:
        return False
    if label == BULLISH_STRUCTURE:
        return direction.upper() == "LONG"
    if label == BEARISH_STRUCTURE:
        return direction.upper() == "SHORT"
    return False
