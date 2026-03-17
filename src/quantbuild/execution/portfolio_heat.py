"""Portfolio Heat Engine — correlation-aware position risk management.

Instead of naive "max 3 positions", this computes effective portfolio heat
by weighting each position's risk contribution through a correlation matrix.

effective_heat = sum(position_risk_i * correlation_weight_i)

This prevents hidden cluster risk from correlated instruments losing together.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Empirical daily return correlations (2021-2026 backtest data)
# Updated from cross_instrument_runner.py results
DEFAULT_CORRELATION_MATRIX = {
    ("XAUUSD", "XAUUSD"): 1.00,
    ("XAUUSD", "GBPUSD"): -0.03,
    ("XAUUSD", "USDJPY"): -0.001,
    ("XAUUSD", "NAS100"): 0.05,
    ("GBPUSD", "GBPUSD"): 1.00,
    ("GBPUSD", "USDJPY"): -0.001,
    ("GBPUSD", "NAS100"): 0.02,
    ("USDJPY", "USDJPY"): 1.00,
    ("USDJPY", "NAS100"): -0.10,
    ("NAS100", "NAS100"): 1.00,
    ("XAUUSD", "EURUSD"): 0.15,
    ("GBPUSD", "EURUSD"): 0.55,
    ("USDJPY", "EURUSD"): -0.25,
    ("EURUSD", "EURUSD"): 1.00,
}


def _get_correlation(sym_a: str, sym_b: str, matrix: Dict = None) -> float:
    """Get pairwise correlation, symmetric lookup."""
    m = matrix or DEFAULT_CORRELATION_MATRIX
    return m.get((sym_a, sym_b), m.get((sym_b, sym_a), 0.0))


class OpenPosition:
    """Lightweight position tracker for heat calculation."""
    __slots__ = ("symbol", "direction", "risk_pct", "asset_class", "regime", "open_time")

    def __init__(self, symbol: str, direction: str, risk_pct: float,
                 asset_class: str = "", regime: str = "", open_time: Optional[datetime] = None):
        self.symbol = symbol
        self.direction = direction
        self.risk_pct = risk_pct
        self.asset_class = asset_class
        self.regime = regime
        self.open_time = open_time


class PortfolioHeatEngine:
    """Correlation-aware portfolio risk manager.

    Tracks open positions and computes effective heat that accounts
    for inter-instrument correlations rather than just counting positions.
    """

    def __init__(self, config: Dict[str, Any]):
        self._max_heat_pct: float = config.get("max_portfolio_heat_pct", 6.0)
        self._max_instrument_heat: float = config.get("max_instrument_heat_pct", 3.0)
        self._max_correlated: int = config.get("max_correlated_exposure", 2)
        self._max_same_direction: int = config.get("max_same_direction", 4)
        self._correlation_matrix: Dict = config.get("correlation_matrix", DEFAULT_CORRELATION_MATRIX)
        self._positions: List[OpenPosition] = []

    @property
    def open_positions(self) -> List[OpenPosition]:
        return list(self._positions)

    @property
    def naive_heat(self) -> float:
        """Simple sum of all position risk."""
        return sum(p.risk_pct for p in self._positions)

    @property
    def effective_heat(self) -> float:
        """Correlation-weighted portfolio heat.

        For uncorrelated positions, effective heat < naive heat (diversification).
        For correlated positions, effective heat ~ naive heat (cluster risk).
        """
        if not self._positions:
            return 0.0

        # Portfolio variance = sum_i sum_j (w_i * w_j * rho_ij)
        total_var = 0.0
        for i, pi in enumerate(self._positions):
            for j, pj in enumerate(self._positions):
                rho = _get_correlation(pi.symbol, pj.symbol, self._correlation_matrix)
                # Same direction = positive correlation contribution
                # Opposite direction = negative (hedging)
                direction_sign = 1.0 if pi.direction == pj.direction else -1.0
                total_var += pi.risk_pct * pj.risk_pct * rho * direction_sign

        # Effective heat = sqrt(portfolio variance), capped at naive heat
        if total_var <= 0:
            return 0.0
        effective = total_var ** 0.5
        return min(effective, self.naive_heat)

    def instrument_heat(self, symbol: str) -> float:
        """Total risk allocated to one instrument."""
        return sum(p.risk_pct for p in self._positions if p.symbol == symbol)

    def same_direction_count(self, direction: str) -> int:
        return sum(1 for p in self._positions if p.direction == direction)

    def correlated_count(self, symbol: str, threshold: float = 0.3) -> int:
        """Count open positions correlated above threshold with given symbol."""
        count = 0
        for p in self._positions:
            if p.symbol == symbol:
                count += 1
            elif abs(_get_correlation(p.symbol, symbol, self._correlation_matrix)) >= threshold:
                count += 1
        return count

    def can_open(self, symbol: str, direction: str, risk_pct: float,
                 asset_class: str = "") -> Tuple[bool, str]:
        """Check if a new position passes all heat constraints.

        Returns (allowed, reason).
        """
        # Max effective heat
        projected = self.effective_heat
        # Approximate: add risk and check
        if self.naive_heat + risk_pct > self._max_heat_pct * 1.5:
            return False, f"naive_heat ({self.naive_heat:.1f}% + {risk_pct:.1f}%) exceeds limit"

        if projected + risk_pct > self._max_heat_pct:
            return False, f"effective_heat ({projected:.1f}% + {risk_pct:.1f}%) > {self._max_heat_pct}%"

        # Max per instrument
        inst_heat = self.instrument_heat(symbol)
        if inst_heat + risk_pct > self._max_instrument_heat:
            return False, f"instrument_heat {symbol} ({inst_heat:.1f}% + {risk_pct:.1f}%) > {self._max_instrument_heat}%"

        # Correlated exposure
        corr_count = self.correlated_count(symbol)
        if corr_count >= self._max_correlated:
            return False, f"correlated_exposure ({corr_count} >= {self._max_correlated})"

        # Same direction limit
        dir_count = self.same_direction_count(direction)
        if dir_count >= self._max_same_direction:
            return False, f"same_direction ({dir_count} >= {self._max_same_direction})"

        return True, "ok"

    def add_position(self, symbol: str, direction: str, risk_pct: float,
                     asset_class: str = "", regime: str = "") -> OpenPosition:
        pos = OpenPosition(symbol, direction, risk_pct, asset_class, regime, datetime.utcnow())
        self._positions.append(pos)
        logger.debug("Heat +%.2f%% %s %s (effective: %.2f%%)",
                      risk_pct, direction, symbol, self.effective_heat)
        return pos

    def remove_position(self, symbol: str, direction: str = "") -> bool:
        for i, p in enumerate(self._positions):
            if p.symbol == symbol and (not direction or p.direction == direction):
                self._positions.pop(i)
                logger.debug("Heat -%.2f%% %s (effective: %.2f%%)",
                              p.risk_pct, symbol, self.effective_heat)
                return True
        return False

    def clear(self):
        self._positions.clear()

    def get_status(self) -> Dict[str, Any]:
        return {
            "positions": len(self._positions),
            "naive_heat": round(self.naive_heat, 2),
            "effective_heat": round(self.effective_heat, 2),
            "max_heat": self._max_heat_pct,
            "utilization": round(100 * self.effective_heat / self._max_heat_pct, 1) if self._max_heat_pct else 0,
            "per_instrument": {
                sym: round(self.instrument_heat(sym), 2)
                for sym in set(p.symbol for p in self._positions)
            },
        }
