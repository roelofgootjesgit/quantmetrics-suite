"""Smoke tests for JSONL → DataFrame → report formatters."""

from __future__ import annotations

from pathlib import Path

from quantmetrics_analytics.analysis.event_summary import format_event_summary
from quantmetrics_analytics.analysis.no_trade_analysis import format_no_trade_analysis
from quantmetrics_analytics.analysis.signal_funnel import format_signal_funnel
from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths
from quantmetrics_analytics.processing.normalize import events_to_dataframe

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_events.jsonl"


def test_load_normalize_summary() -> None:
    events = load_events_from_paths([_FIXTURE])
    df = events_to_dataframe(events)
    assert len(df) == 5
    assert "payload_decision" in df.columns
    text = format_event_summary(df)
    assert "Total events: 5" in text
    assert "trade_action" in text


def test_no_trade_and_funnel() -> None:
    events = load_events_from_paths([_FIXTURE])
    df = events_to_dataframe(events)
    nt = format_no_trade_analysis(df)
    assert "cooldown_active" in nt
    assert "NO_ACTION" in nt or "NO_ACTION events" in nt
    fn = format_signal_funnel(df)
    assert "signal_detected" in fn
    assert "ENTER/REVERSE" in fn


def test_cli_exit_code(tmp_path: Path) -> None:
    from quantmetrics_analytics.cli.run_analysis import run

    assert run(argv=["--jsonl", str(_FIXTURE), "--reports", "summary"]) == 0
