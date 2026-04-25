from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent
DEMO_FILE = ROOT / "examples" / "demo_quantlog_events.jsonl"

for rel in ("quantlog/src", "quantanalytics/src"):
    src_path = ROOT / rel
    if src_path.is_dir():
        sys.path.insert(0, str(src_path))

from quantanalytics.guard_attribution.loader import load_events
from quantlog.validate.validator import validate_path


def _funnel_counts(event_types: Counter[str]) -> dict[str, int]:
    return {
        "detected": int(event_types.get("signal_detected", 0)),
        "evaluated": int(event_types.get("signal_evaluated", 0)),
        "action": int(event_types.get("trade_action", 0)),
        "filled": int(event_types.get("order_filled", 0) + event_types.get("trade_executed", 0)),
        "closed": int(event_types.get("trade_closed", 0)),
    }


def _guard_attribution(events: list[dict]) -> Counter[str]:
    rows: Counter[str] = Counter()
    for event in events:
        if event.get("event_type") != "risk_guard_decision":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        guard_name = str(payload.get("guard_name", "unknown_guard")).strip() or "unknown_guard"
        decision = str(payload.get("decision", "UNKNOWN")).strip().upper() or "UNKNOWN"
        rows[f"{guard_name}:{decision}"] += 1
    return rows


def _funnel_conversion_rates(funnel: dict[str, int]) -> dict[str, float]:
    def _rate(numerator_key: str, denominator_key: str) -> float:
        denominator = funnel.get(denominator_key, 0)
        if denominator <= 0:
            return 0.0
        return (funnel.get(numerator_key, 0) / denominator) * 100.0

    return {
        "detected_to_evaluated": _rate("evaluated", "detected"),
        "evaluated_to_action": _rate("action", "evaluated"),
        "action_to_filled": _rate("filled", "action"),
    }


def _guard_dominance(events: list[dict]) -> tuple[str, float]:
    block_counts: Counter[str] = Counter()
    for event in events:
        if event.get("event_type") != "risk_guard_decision":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("decision", "")).strip().upper() != "BLOCK":
            continue
        guard_name = str(payload.get("guard_name", "unknown_guard")).strip() or "unknown_guard"
        block_counts[guard_name] += 1
    if not block_counts:
        return ("none", 0.0)
    top_guard, top_count = block_counts.most_common(1)[0]
    total_blocks = sum(block_counts.values())
    return (top_guard, (top_count / total_blocks) * 100.0)


def _trade_performance(events: list[dict]) -> dict[str, Any]:
    pnl_r_values: list[float] = []
    for event in events:
        if event.get("event_type") != "trade_closed":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        pnl_r = payload.get("pnl_r")
        if isinstance(pnl_r, (int, float)):
            pnl_r_values.append(float(pnl_r))

    sample_size = len(pnl_r_values)
    wins = [value for value in pnl_r_values if value > 0.0]
    losses = [value for value in pnl_r_values if value < 0.0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    winrate = ((len(wins) / sample_size) * 100.0) if sample_size > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    expectancy = (sum(pnl_r_values) / sample_size) if sample_size > 0 else 0.0

    return {
        "sample_size": sample_size,
        "winrate": winrate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
    }


def _verdict(
    *,
    funnel: dict[str, int],
    validation_errors: int,
    performance: dict[str, Any],
    minimum_sample_size: int = 30,
) -> str:
    if validation_errors > 0:
        return "REJECT"
    ordered = ["detected", "evaluated", "action", "filled", "closed"]
    if any(funnel[name] <= 0 for name in ordered):
        return "VALIDATION_REQUIRED"
    if any(funnel[ordered[idx]] > funnel[ordered[idx - 1]] for idx in range(1, len(ordered))):
        return "VALIDATION_REQUIRED"
    sample_size = int(performance.get("sample_size", 0))
    expectancy = float(performance.get("expectancy", 0.0))
    if sample_size < minimum_sample_size:
        return "VALIDATION_REQUIRED"
    if expectancy <= 0.0:
        return "VALIDATION_REQUIRED"
    return "PASS"


def main() -> int:
    events = load_events(str(DEMO_FILE))
    report = validate_path(DEMO_FILE)

    event_types = Counter(str(event.get("event_type", "UNKNOWN")) for event in events)
    funnel = _funnel_counts(event_types)
    conversion_rates = _funnel_conversion_rates(funnel)
    guard_rows = _guard_attribution(events)
    top_blocking_guard, top_block_share = _guard_dominance(events)
    performance = _trade_performance(events)
    validation_errors = sum(1 for issue in report.issues if issue.level == "error")
    verdict = _verdict(funnel=funnel, validation_errors=validation_errors, performance=performance)

    print(f"Demo file: {DEMO_FILE}")
    print(f"Total events: {len(events)}")
    print("Event counts by type:")
    for name, count in sorted(event_types.items()):
        print(f"  - {name}: {count}")

    print("Funnel: detected -> evaluated -> action -> filled -> closed")
    print(
        "  "
        f"{funnel['detected']} -> {funnel['evaluated']} -> "
        f"{funnel['action']} -> {funnel['filled']} -> {funnel['closed']}"
    )
    print("Conversion rates:")
    print(f"  - detected -> evaluated: {conversion_rates['detected_to_evaluated']:.0f}%")
    print(f"  - evaluated -> action: {conversion_rates['evaluated_to_action']:.0f}%")
    print(f"  - action -> filled: {conversion_rates['action_to_filled']:.0f}%")

    print("Guard attribution:")
    if guard_rows:
        for key, count in sorted(guard_rows.items()):
            print(f"  - {key}: {count}")
    else:
        print("  - none")
    print(f"Top blocking guard: {top_blocking_guard} ({top_block_share:.0f}% of blocks)")

    print("Trade performance:")
    print(f"  - winrate: {performance['winrate']:.0f}%")
    pf = performance["profit_factor"]
    pf_str = "inf" if pf == float("inf") else f"{pf:.2f}"
    print(f"  - profit_factor: {pf_str}")
    print(f"  - expectancy: {performance['expectancy']:+.2f}R")
    print(f"  - sample_size: {performance['sample_size']}")

    print(f"Validation errors: {validation_errors}")
    print(f"Verdict: {verdict}")
    return 0 if verdict != "REJECT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
