from __future__ import annotations

from .models import DecisionCycle


def _label(score: int, unknown: bool) -> str:
    if unknown:
        return "UNKNOWN"
    if score >= 2:
        return "HIGH_QUALITY"
    if score >= 0:
        return "MEDIUM_QUALITY"
    return "LOW_QUALITY"


def score_decision_cycles(cycles: list[DecisionCycle]) -> list[dict]:
    rows: list[dict] = []

    for cycle in cycles:
        score = 0
        unknown = False
        warning_tags = set(cycle.warnings)

        if cycle.trade_closed and cycle.pnl_r is not None:
            if cycle.pnl_r > 0:
                score += 2
            elif cycle.pnl_r < 0:
                score -= 2
        elif cycle.trade_closed and cycle.pnl_r is None:
            unknown = True

        if cycle.mfe_r is not None and cycle.mfe_r > 0:
            score += 1
        if cycle.mae_r is not None and cycle.mfe_r is not None and cycle.mae_r > cycle.mfe_r:
            score -= 1

        if cycle.incomplete:
            score -= 1
        if cycle.trade_action is None:
            score -= 2
            warning_tags.add("TRADE_ACTION_MISSING")
        if cycle.trade_executed and cycle.risk_guard_decision is None:
            score -= 2
            warning_tags.add("EXECUTION_WITHOUT_DECISION")

        if cycle.trade_closed is None and cycle.trade_executed is None:
            unknown = True

        rows.append(
            {
                "decision_cycle_id": cycle.decision_cycle_id,
                "run_id": cycle.run_id,
                "symbol": cycle.symbol,
                "regime": cycle.regime,
                "session": cycle.session,
                "action": cycle.action,
                "guard_name": cycle.guard_name,
                "guard_decision": cycle.guard_decision,
                "pnl_r": cycle.pnl_r,
                "mfe_r": cycle.mfe_r,
                "mae_r": cycle.mae_r,
                "quality_score": score,
                "quality_label": _label(score, unknown),
                "warnings": sorted(warning_tags),
            }
        )
    return rows

