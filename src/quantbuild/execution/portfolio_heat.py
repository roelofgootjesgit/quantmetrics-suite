"""Portfolio Heat Engine — correlation-aware position risk management.

Instead of naive "max 3 positions", this computes effective portfolio heat
by weighting each position's risk contribution through a correlation matrix.

effective_heat = sum(position_risk_i * correlation_weight_i)

This prevents hidden cluster risk from correlated instruments losing together.

Cluster Risk Engine (v1):
  - Defines FX clusters (e.g. GBP+NZD = risk-on commodity FX)
  - Caps concurrent trades and combined heat per cluster
  - Applies correlation-aware sizing: reduces risk when cluster peer is active
  - Instrument priority: XAU > GBP > NZD > JPY > CHF for conflict resolution
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Empirical daily return correlations (2021-2026 backtest data)
# Updated from cross_instrument_runner.py results
DEFAULT_CORRELATION_MATRIX = {
    # Self
    ("XAUUSD", "XAUUSD"): 1.00,
    ("GBPUSD", "GBPUSD"): 1.00,
    ("USDJPY", "USDJPY"): 1.00,
    ("NAS100", "NAS100"): 1.00,
    ("EURUSD", "EURUSD"): 1.00,
    ("USDCHF", "USDCHF"): 1.00,
    ("NZDUSD", "NZDUSD"): 1.00,
    # Core cross-correlations
    ("XAUUSD", "GBPUSD"): -0.03,
    ("XAUUSD", "USDJPY"): -0.001,
    ("XAUUSD", "USDCHF"): -0.15,
    ("XAUUSD", "NZDUSD"): 0.10,
    ("XAUUSD", "EURUSD"): 0.15,
    ("GBPUSD", "USDJPY"): -0.001,
    ("GBPUSD", "USDCHF"): -0.55,
    ("GBPUSD", "NZDUSD"): 0.60,
    ("GBPUSD", "EURUSD"): 0.55,
    ("USDJPY", "USDCHF"): 0.50,
    ("USDJPY", "NZDUSD"): -0.30,
    ("USDJPY", "EURUSD"): -0.25,
    ("USDCHF", "NZDUSD"): -0.55,
    ("USDCHF", "EURUSD"): -0.85,
    ("NZDUSD", "EURUSD"): 0.55,
    # Throughput
    ("XAUUSD", "NAS100"): 0.05,
    ("GBPUSD", "NAS100"): 0.02,
    ("USDJPY", "NAS100"): -0.10,
    ("USDCHF", "NAS100"): -0.05,
    ("NZDUSD", "NAS100"): 0.10,
}


def _get_correlation(sym_a: str, sym_b: str, matrix: Dict = None) -> float:
    """Get pairwise correlation, symmetric lookup."""
    m = matrix or DEFAULT_CORRELATION_MATRIX
    return m.get((sym_a, sym_b), m.get((sym_b, sym_a), 0.0))


# ── Cluster Definitions ──────────────────────────────────────────────

DEFAULT_CLUSTERS = {
    "risk_on_fx": {
        "instruments": ["GBPUSD", "NZDUSD"],
        "max_concurrent": 2,
        "max_heat_pct": 1.5,
        "sizing_penalty": 0.7,
        "reason": "GBP+NZD corr +0.60 — risk-on commodity FX cluster",
    },
    "usd_bloc": {
        "instruments": ["USDJPY", "USDCHF"],
        "max_concurrent": 2,
        "max_heat_pct": 1.5,
        "sizing_penalty": 0.8,
        "reason": "JPY+CHF corr +0.50 — USD strength cluster",
    },
    "chf_eur_inverse": {
        "instruments": ["USDCHF", "EURUSD"],
        "max_concurrent": 1,
        "max_heat_pct": 1.0,
        "sizing_penalty": 0.6,
        "reason": "CHF+EUR corr -0.85 — near-mirror, don't trade both",
    },
}

# Higher number = higher priority. Conflicts resolved by taking the higher-priority instrument.
DEFAULT_INSTRUMENT_PRIORITY = {
    "XAUUSD": 100,
    "GBPUSD": 80,
    "NZDUSD": 70,
    "USDJPY": 60,
    "USDCHF": 50,
    "EURUSD": 40,
    "NAS100": 30,
}


class ClusterRiskEngine:
    """Manages FX cluster constraints and correlation-aware position sizing.

    Usage:
        cluster_engine = ClusterRiskEngine(config)
        risk_mult = cluster_engine.get_sizing_multiplier("NZDUSD", open_positions)
        allowed, reason = cluster_engine.can_open("NZDUSD", open_positions)
    """

    def __init__(self, config: Dict[str, Any]):
        cluster_cfg = config.get("clusters", {})
        self._clusters: Dict[str, Dict] = cluster_cfg if cluster_cfg else DEFAULT_CLUSTERS
        self._priority: Dict[str, int] = config.get(
            "instrument_priority", DEFAULT_INSTRUMENT_PRIORITY
        )

        self._instrument_to_clusters: Dict[str, List[str]] = {}
        for cname, cdef in self._clusters.items():
            for inst in cdef.get("instruments", []):
                self._instrument_to_clusters.setdefault(inst, []).append(cname)

    def get_clusters_for(self, symbol: str) -> List[str]:
        return self._instrument_to_clusters.get(symbol, [])

    def get_priority(self, symbol: str) -> int:
        return self._priority.get(symbol, 0)

    def can_open_in_cluster(
        self, symbol: str, positions: List["OpenPosition"]
    ) -> Tuple[bool, str]:
        """Check all cluster constraints for a new position."""
        for cname in self.get_clusters_for(symbol):
            cdef = self._clusters[cname]
            cluster_instruments = set(cdef.get("instruments", []))
            max_concurrent = cdef.get("max_concurrent", 2)

            active_in_cluster = [
                p for p in positions if p.symbol in cluster_instruments
            ]

            if len(active_in_cluster) >= max_concurrent:
                return False, (
                    f"cluster '{cname}' full: {len(active_in_cluster)}"
                    f" >= {max_concurrent} ({cdef.get('reason', '')})"
                )

            max_heat = cdef.get("max_heat_pct", 999)
            cluster_heat = sum(p.risk_pct for p in active_in_cluster)
            if cluster_heat >= max_heat:
                return False, (
                    f"cluster '{cname}' heat {cluster_heat:.2f}%"
                    f" >= {max_heat}%"
                )

        return True, "ok"

    def get_sizing_multiplier(
        self, symbol: str, positions: List["OpenPosition"]
    ) -> float:
        """Get risk multiplier based on active cluster peers.

        If a correlated peer is already open, reduce risk for this instrument.
        Returns 1.0 if no cluster peer is active, otherwise the penalty factor.
        """
        worst_penalty = 1.0

        for cname in self.get_clusters_for(symbol):
            cdef = self._clusters[cname]
            cluster_instruments = set(cdef.get("instruments", []))
            penalty = cdef.get("sizing_penalty", 1.0)

            peer_active = any(
                p.symbol in cluster_instruments and p.symbol != symbol
                for p in positions
            )
            if peer_active:
                worst_penalty = min(worst_penalty, penalty)

        return worst_penalty

    def resolve_priority(self, symbol_a: str, symbol_b: str) -> str:
        """Return the higher-priority instrument (for conflict resolution)."""
        pa = self.get_priority(symbol_a)
        pb = self.get_priority(symbol_b)
        return symbol_a if pa >= pb else symbol_b

    def get_status(self, positions: List["OpenPosition"]) -> Dict[str, Any]:
        status = {}
        for cname, cdef in self._clusters.items():
            cluster_instruments = set(cdef.get("instruments", []))
            active = [p for p in positions if p.symbol in cluster_instruments]
            status[cname] = {
                "instruments": list(cluster_instruments),
                "active": len(active),
                "max_concurrent": cdef.get("max_concurrent", 2),
                "heat": round(sum(p.risk_pct for p in active), 3),
                "max_heat": cdef.get("max_heat_pct", 999),
            }
        return status


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
        self._cluster_engine = ClusterRiskEngine(config)

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

    @property
    def cluster_engine(self) -> ClusterRiskEngine:
        return self._cluster_engine

    def get_cluster_adjusted_risk(self, symbol: str, base_risk_pct: float) -> float:
        """Apply cluster sizing penalty if a correlated peer is already open."""
        mult = self._cluster_engine.get_sizing_multiplier(symbol, self._positions)
        adjusted = base_risk_pct * mult
        if mult < 1.0:
            logger.info("Cluster sizing: %s risk %.2f%% -> %.2f%% (mult %.2f)",
                        symbol, base_risk_pct, adjusted, mult)
        return adjusted

    def can_open(self, symbol: str, direction: str, risk_pct: float,
                 asset_class: str = "") -> Tuple[bool, str]:
        """Check if a new position passes all heat + cluster constraints.

        Returns (allowed, reason).
        """
        # Cluster constraints (FX cluster caps)
        cluster_ok, cluster_reason = self._cluster_engine.can_open_in_cluster(
            symbol, self._positions
        )
        if not cluster_ok:
            return False, f"cluster_block: {cluster_reason}"

        # Max effective heat
        projected = self.effective_heat
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
            "clusters": self._cluster_engine.get_status(self._positions),
        }
