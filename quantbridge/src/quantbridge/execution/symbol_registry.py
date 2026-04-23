from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class SymbolSpec:
    internal_symbol: str
    broker_symbol: str
    precision: int
    pip_size: float
    min_volume: float
    volume_step: float


_SYMBOLS: Dict[str, Dict[str, SymbolSpec]] = {
    "ctrader": {
        "XAUUSD": SymbolSpec("XAUUSD", "XAUUSD", 2, 0.01, 1.0, 1.0),
        "EURUSD": SymbolSpec("EURUSD", "EURUSD", 5, 0.0001, 1000.0, 1000.0),
    }
}


def get_symbol_spec(provider: str, internal_symbol: str) -> Optional[SymbolSpec]:
    p = str(provider).lower()
    key = (internal_symbol or "").replace("_", "").upper()
    return _SYMBOLS.get(p, {}).get(key)


def map_symbol(provider: str, internal_symbol: str) -> str:
    spec = get_symbol_spec(provider, internal_symbol)
    return spec.broker_symbol if spec else internal_symbol


def normalize_units(provider: str, internal_symbol: str, units: float) -> float:
    spec = get_symbol_spec(provider, internal_symbol)
    if spec is None:
        return float(units)
    u = max(spec.min_volume, float(units))
    steps = round(u / spec.volume_step)
    return float(max(spec.min_volume, steps * spec.volume_step))
