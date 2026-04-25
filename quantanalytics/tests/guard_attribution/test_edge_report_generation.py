from __future__ import annotations

from quantanalytics.guard_attribution.decision_cycles import reconstruct_decision_cycles
from quantanalytics.guard_attribution.report import generate_edge_report


def test_edge_report_generation(tmp_path, sample_cycle_events):
    cycles = reconstruct_decision_cycles(sample_cycle_events)
    out_file = tmp_path / "EDGE_REPORT.md"

    result = generate_edge_report(
        run_id="qb_run_20260425T042136Z_dbd1b0cc",
        source_events="sample.jsonl",
        events_count=len(sample_cycle_events),
        cycles=cycles,
        guard_attribution={"guards": []},
        stability={"regime": [], "session": []},
        decision_quality=[],
        warnings=[],
        edge_verdict={
            "edge_verdict": "PROMISING_BUT_UNPROVEN",
            "confidence": "LOW",
            "main_strength": "n/a",
            "main_risk": "n/a",
            "recommended_next_action": "n/a",
        },
        throughput={
            "raw_signals_detected": 1,
            "signals_after_filters": 1,
            "signals_executed": 1,
            "filter_kill_ratio": 0.0,
            "execution_ratio": 1.0,
            "throughput_rates": {"trades_per_month": 0.5, "months_span_inclusive": 2},
            "breakdowns": {
                "guard_blocks": {"spread_guard": 1},
                "filter_reasons": {"session_blocked": 1},
                "regime_guard_blocks": {"trend:spread_guard": 1},
                "session_guard_blocks": {"Asia:spread_guard": 1},
            },
        },
        output_path=str(out_file),
    )

    assert result.exists()
    content = result.read_text(encoding="utf-8")
    assert "# EDGE REPORT" in content
    assert "## 3. Throughput Funnel (Diagnostics)" in content
    assert "## 9. Final Verdict" in content

