"""Guard Attribution MVP — slice counterfactual smoke tests."""

from __future__ import annotations

from pathlib import Path

from quantmetrics_analytics.guard_attribution.pipeline import run_guard_attribution
from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "guard_attribution_mini.jsonl"


def test_guard_attribution_pipeline_slice_estimate() -> None:
    events = load_events_from_paths([_FIXTURE])
    rid = "ga-mvp"
    events = [e for e in events if e.get("run_id") == rid]
    payload = run_guard_attribution(events, run_id=rid, min_slice_n=1)

    assert payload["meta"]["total_blocks"] == 1
    assert payload["meta"]["executed_trades"] == 1
    tbl = payload["guard_score_table"]
    assert len(tbl) == 1
    assert tbl[0]["guard_name"] == "regime_profile"
    assert tbl[0]["estimated_missed_winners_count"] == 1
    assert tbl[0]["mean_estimated_r"] == 2.0


def test_guard_attribution_cli(tmp_path: Path) -> None:
    from quantmetrics_analytics.cli.guard_attribution import run

    buf_calls: list[str] = []

    class Buf:
        def write(self, s: str) -> None:
            buf_calls.append(s)

        def flush(self) -> None:
            pass

    rc = run(
        argv=[
            "--run-id",
            "ga-mvp",
            "--jsonl",
            str(_FIXTURE),
            "--output-dir",
            str(tmp_path),
            "--min-slice-n",
            "1",
        ],
        stdout=Buf(),
    )
    assert rc == 0
    outs = list(tmp_path.glob("guard_attribution_ga-mvp.*"))
    assert len(outs) == 2
