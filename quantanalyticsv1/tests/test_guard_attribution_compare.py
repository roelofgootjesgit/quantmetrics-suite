"""Level B — baseline vs variant run comparison."""

from __future__ import annotations

from pathlib import Path

from quantmetrics_analytics.cli.guard_attribution_compare import run as run_compare_cli
from quantmetrics_analytics.guard_attribution.rerun_compare import compare_guard_rerun_runs
from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "guard_rerun_compare.jsonl"


def test_compare_guard_rerun_pipeline() -> None:
    events = load_events_from_paths([_FIXTURE])
    eb = [e for e in events if e.get("run_id") == "base-run"]
    ev = [e for e in events if e.get("run_id") == "var-run"]
    payload = compare_guard_rerun_runs(eb, baseline_run_id="base-run", events_variant=ev, variant_run_id="var-run")

    assert payload["baseline_metrics"]["trade_count"] == 2
    assert payload["variant_metrics"]["trade_count"] == 3
    assert payload["delta_trade_metrics"]["delta_trade_count"] == 1
    assert payload["guard_blocks_table"]
    rp = next(r for r in payload["guard_blocks_table"] if r["guard_name"] == "regime_profile")
    assert rp["delta_blocks"] == -1


def test_compare_cli(tmp_path: Path) -> None:
    rc = run_compare_cli(
        argv=[
            "--baseline-run-id",
            "base-run",
            "--variant-run-id",
            "var-run",
            "--jsonl",
            str(_FIXTURE),
            "--output-dir",
            str(tmp_path),
            "--guard-focus",
            "regime_profile",
        ]
    )
    assert rc == 0
    outs = list(tmp_path.glob("guard_attribution_compare_*_vs_*.json"))
    assert len(outs) == 1
