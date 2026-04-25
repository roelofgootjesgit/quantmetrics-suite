from __future__ import annotations

from pathlib import Path

from quantlog.validate.validator import validate_path


def test_demo_quantlog_events_validate_without_errors() -> None:
    demo_file = Path(__file__).resolve().parents[1] / "examples" / "demo_quantlog_events.jsonl"
    report = validate_path(demo_file)
    errors = [issue for issue in report.issues if issue.level == "error"]
    assert errors == []
    assert report.events_valid == 6
