"""Execution Quality Logger — tracks slippage, spreads, and fill quality.

Execution quality is the silent killer of trading strategies.
A strategy with 0.41R expectancy loses its edge at 0.3R slippage.

This logger tracks fill quality per instrument, session, and regime
to identify execution patterns and degrade gracefully.
"""
import csv
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FillRecord:
    """Single execution record."""
    timestamp: datetime
    symbol: str
    direction: str
    session: str
    regime: str
    expected_price: float
    actual_price: float
    spread_pips: float
    slippage_r: float
    order_type: str
    was_rejected: bool = False
    reject_reason: str = ""


class ExecutionQualityLogger:
    """Tracks and analyzes execution quality metrics.

    Provides:
    - Per-instrument/session/regime slippage distribution
    - Fill quality scoring
    - Adaptive entry type recommendations
    - Reject analytics (why trades were blocked)
    """

    def __init__(self, config: Dict[str, Any], log_dir: str = "data/execution_logs"):
        self._log_dir = log_dir
        self._records: List[FillRecord] = []
        self._rejects: List[FillRecord] = []

        # Thresholds for quality scoring
        exec_cfg = config.get("execution_quality", {})
        self._good_slippage: float = exec_cfg.get("good_slippage_r", 0.05)
        self._warn_slippage: float = exec_cfg.get("warn_slippage_r", 0.15)
        self._good_spread: float = exec_cfg.get("good_spread_pips", 2.0)
        self._warn_spread: float = exec_cfg.get("warn_spread_pips", 4.0)

    def record_fill(self, symbol: str, direction: str, session: str, regime: str,
                    expected_price: float, actual_price: float,
                    spread_pips: float, slippage_r: float,
                    order_type: str = "market") -> FillRecord:
        """Log a successful fill."""
        rec = FillRecord(
            timestamp=datetime.utcnow(), symbol=symbol, direction=direction,
            session=session, regime=regime, expected_price=expected_price,
            actual_price=actual_price, spread_pips=spread_pips,
            slippage_r=slippage_r, order_type=order_type,
        )
        self._records.append(rec)

        if abs(slippage_r) > self._warn_slippage:
            logger.warning("HIGH SLIPPAGE: %s %s %.3fR", symbol, session, slippage_r)

        return rec

    def record_reject(self, symbol: str, direction: str, session: str, regime: str,
                      spread_pips: float, reason: str) -> FillRecord:
        """Log a rejected trade attempt."""
        rec = FillRecord(
            timestamp=datetime.utcnow(), symbol=symbol, direction=direction,
            session=session, regime=regime, expected_price=0, actual_price=0,
            spread_pips=spread_pips, slippage_r=0, order_type="rejected",
            was_rejected=True, reject_reason=reason,
        )
        self._rejects.append(rec)
        return rec

    def _group_stats(self, records: List[FillRecord], key_fn) -> Dict[str, Dict]:
        """Compute stats grouped by a key function."""
        groups = defaultdict(list)
        for r in records:
            groups[key_fn(r)].append(r)

        stats = {}
        for key, recs in groups.items():
            slippages = [r.slippage_r for r in recs]
            spreads = [r.spread_pips for r in recs]
            n = len(recs)
            stats[key] = {
                "count": n,
                "avg_slippage_r": sum(slippages) / n,
                "max_slippage_r": max(slippages),
                "avg_spread_pips": sum(spreads) / n,
                "max_spread_pips": max(spreads),
                "quality_score": self._quality_score(slippages, spreads),
            }
        return stats

    def _quality_score(self, slippages: List[float], spreads: List[float]) -> str:
        """Rate execution quality: A/B/C/F."""
        avg_slip = sum(slippages) / len(slippages) if slippages else 0
        avg_spread = sum(spreads) / len(spreads) if spreads else 0

        if avg_slip <= self._good_slippage and avg_spread <= self._good_spread:
            return "A"
        elif avg_slip <= self._warn_slippage and avg_spread <= self._warn_spread:
            return "B"
        elif avg_slip <= self._warn_slippage * 1.5:
            return "C"
        return "F"

    def stats_by_instrument(self) -> Dict[str, Dict]:
        return self._group_stats(self._records, lambda r: r.symbol)

    def stats_by_session(self) -> Dict[str, Dict]:
        return self._group_stats(self._records, lambda r: f"{r.symbol}_{r.session}")

    def stats_by_regime(self) -> Dict[str, Dict]:
        return self._group_stats(self._records, lambda r: f"{r.symbol}_{r.regime}")

    def reject_analytics(self) -> Dict[str, Any]:
        """Analyze why trades were rejected."""
        if not self._rejects:
            return {"total": 0}

        by_reason = defaultdict(int)
        by_symbol = defaultdict(int)
        by_session = defaultdict(int)
        for r in self._rejects:
            by_reason[r.reject_reason] += 1
            by_symbol[r.symbol] += 1
            by_session[f"{r.symbol}_{r.session}"] += 1

        return {
            "total": len(self._rejects),
            "by_reason": dict(by_reason),
            "by_symbol": dict(by_symbol),
            "by_session": dict(by_session),
        }

    def recommend_order_type(self, symbol: str, session: str,
                             current_spread: float, current_atr: float) -> str:
        """Recommend order type based on historical execution quality.

        Returns: 'market', 'limit', or 'skip'
        """
        relevant = [r for r in self._records
                     if r.symbol == symbol and r.session == session]

        if not relevant:
            if current_spread <= self._good_spread:
                return "market"
            return "limit"

        avg_slip = sum(r.slippage_r for r in relevant) / len(relevant)

        if current_spread > self._warn_spread * 1.5:
            return "skip"
        elif avg_slip > self._warn_slippage or current_spread > self._warn_spread:
            return "limit"
        return "market"

    def save_to_csv(self, path: str = ""):
        """Persist execution records to CSV."""
        out = path or os.path.join(self._log_dir, "fills.csv")
        os.makedirs(os.path.dirname(out), exist_ok=True)

        with open(out, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "symbol", "direction", "session", "regime",
                "expected_price", "actual_price", "spread_pips",
                "slippage_r", "order_type", "rejected", "reject_reason",
            ])
            for r in self._records + self._rejects:
                writer.writerow([
                    r.timestamp.isoformat(), r.symbol, r.direction,
                    r.session, r.regime, r.expected_price, r.actual_price,
                    r.spread_pips, r.slippage_r, r.order_type,
                    r.was_rejected, r.reject_reason,
                ])

    def get_summary(self) -> Dict[str, Any]:
        total = len(self._records)
        if total == 0:
            return {"fills": 0, "rejects": len(self._rejects)}

        slippages = [r.slippage_r for r in self._records]
        return {
            "fills": total,
            "rejects": len(self._rejects),
            "avg_slippage_r": round(sum(slippages) / total, 4),
            "max_slippage_r": round(max(slippages), 4),
            "by_instrument": self.stats_by_instrument(),
            "reject_analytics": self.reject_analytics(),
        }
