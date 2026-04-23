"""Symbol mapping and execution metadata per broker."""
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
        "XAUUSD": SymbolSpec(
            internal_symbol="XAUUSD",
            broker_symbol="XAUUSD",
            precision=2,
            pip_size=0.01,
            min_volume=1.0,
            volume_step=1.0,
        ),
        "EURUSD": SymbolSpec(
            internal_symbol="EURUSD",
            broker_symbol="EURUSD",
            precision=5,
            pip_size=0.0001,
            min_volume=1000.0,
            volume_step=1000.0,
        ),
    },
    "oanda": {
        "XAUUSD": SymbolSpec(
            internal_symbol="XAUUSD",
            broker_symbol="XAU_USD",
            precision=3,
            pip_size=0.01,
            min_volume=1.0,
            volume_step=1.0,
        ),
        "EURUSD": SymbolSpec(
            internal_symbol="EURUSD",
            broker_symbol="EUR_USD",
            precision=5,
            pip_size=0.0001,
            min_volume=1.0,
            volume_step=1.0,
        ),
    },
}


def get_symbol_spec(provider: str, internal_symbol: str) -> Optional[SymbolSpec]:
    p = str(provider or "").lower()
    key = (internal_symbol or "").replace("_", "").upper()
    return _SYMBOLS.get(p, {}).get(key)


def map_symbol(provider: str, internal_symbol: str) -> str:
    spec = get_symbol_spec(provider, internal_symbol)
    if spec:
        return spec.broker_symbol
    if str(provider).lower() == "oanda" and "_" not in internal_symbol:
        # Best-effort fallback to common Oanda naming.
        if len(internal_symbol) == 6:
            return f"{internal_symbol[:3]}_{internal_symbol[3:]}"
    return internal_symbol


def normalize_units(provider: str, internal_symbol: str, units: float) -> float:
    spec = get_symbol_spec(provider, internal_symbol)
    if not spec:
        return float(units)
    u = max(spec.min_volume, float(units))
    steps = round(u / spec.volume_step)
    normalized = steps * spec.volume_step
    return float(max(spec.min_volume, normalized))
