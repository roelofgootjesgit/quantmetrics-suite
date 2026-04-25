from __future__ import annotations

from collections import defaultdict

from .models import DecisionCycle


def _sample_quality(n: int) -> str:
    if n < 20:
        return "INSUFFICIENT_DATA"
    if n < 50:
        return "WEAK_EVIDENCE"
    if n < 100:
        return "USABLE"
    return "STRONGER_EVIDENCE"


def _profit_factor(pnls: list[float]) -> float | None:
    gross_profit = sum(x for x in pnls if x > 0)
    gross_loss = abs(sum(x for x in pnls if x < 0))
    if gross_loss == 0:
        return None if gross_profit == 0 else float("inf")
    return gross_profit / gross_loss


def _verdict(total_cycles: int, expectancy: float | None, pf: float | None, blocked: int) -> tuple[str, str]:
    if total_cycles < 20:
        return "INSUFFICIENT_DATA", "Sample size below minimum threshold"
    if expectancy is None:
        return "UNKNOWN", "No closed-trade outcomes available"
    if expectancy > 0 and (pf is None or pf > 1.2):
        return "EDGE_PROTECTIVE", "Guard allows positive expectancy outcomes"
    if expectancy < 0 and blocked < (total_cycles * 0.2):
        return "EDGE_DESTROYING", "Guard associated with negative expectancy outcomes"
    return "NEUTRAL", "Evidence does not show clear protective or destructive behavior"


def analyze_guards(cycles: list[DecisionCycle]) -> dict:
    grouped: dict[str, list[DecisionCycle]] = defaultdict(list)
    for cycle in cycles:
        grouped[cycle.guard_name or "UNKNOWN_GUARD"].append(cycle)

    guard_rows: list[dict] = []
    for guard_name, guard_cycles in sorted(grouped.items()):
        decisions = [((c.guard_decision or "").upper(), (c.action or "").upper()) for c in guard_cycles]
        pnls = [c.pnl_r for c in guard_cycles if c.trade_closed and c.pnl_r is not None]
        pnl_values = [float(v) for v in pnls]

        total_cycles = len(guard_cycles)
        closed_trades = len(pnl_values)
        wins = sum(1 for value in pnl_values if value > 0)
        avg_pnl = sum(pnl_values) / closed_trades if closed_trades else None
        expectancy = avg_pnl
        pf = _profit_factor(pnl_values)
        verdict, reason = _verdict(total_cycles, expectancy, pf, sum(1 for d, _ in decisions if d == "BLOCK"))

        avg_mfe = None
        avg_mae = None
        mfe_values = [c.mfe_r for c in guard_cycles if c.mfe_r is not None]
        mae_values = [c.mae_r for c in guard_cycles if c.mae_r is not None]
        if mfe_values:
            avg_mfe = sum(mfe_values) / len(mfe_values)
        if mae_values:
            avg_mae = sum(mae_values) / len(mae_values)

        counterfactual_available = any((d == "BLOCK" and c.pnl_r is not None) for c, (d, _) in zip(guard_cycles, decisions))
        if not counterfactual_available and any(d == "BLOCK" for d, _ in decisions):
            reason = "No shadow outcome available for blocked signals"

        guard_rows.append(
            {
                "guard_name": guard_name,
                "total_cycles": total_cycles,
                "allowed_count": sum(1 for d, _ in decisions if d == "ALLOW"),
                "blocked_count": sum(1 for d, _ in decisions if d == "BLOCK"),
                "reduced_count": sum(1 for d, _ in decisions if d == "REDUCE"),
                "delayed_count": sum(1 for d, _ in decisions if d == "DELAY"),
                "no_action_count": sum(1 for _, a in decisions if a == "NO_ACTION"),
                "executed_after_allow": sum(
                    1
                    for c, (d, _) in zip(guard_cycles, decisions)
                    if d == "ALLOW" and c.trade_executed is not None
                ),
                "closed_trades": closed_trades,
                "avg_pnl_r": avg_pnl,
                "expectancy_r": expectancy,
                "win_rate": (wins / closed_trades) if closed_trades else None,
                "profit_factor": pf,
                "avg_mfe_r": avg_mfe,
                "avg_mae_r": avg_mae,
                "sample_quality": _sample_quality(total_cycles),
                "counterfactual_available": counterfactual_available,
                "verdict": verdict,
                "reason": reason,
            }
        )

    return {"guards": guard_rows}

