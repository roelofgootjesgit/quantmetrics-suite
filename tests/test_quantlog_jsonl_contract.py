"""Regression tests: QuantLog-shaped JSONL matches live_runner / QuantLog v1 expectations.

Keeps CI green without cloning QuantLog; align fixture with QuantLog validate-events when possible.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from src.quantbuild.execution.quantlog_emitter import QuantLogEmitter
from src.quantbuild.quantlog_repo import quantbuild_project_root, resolve_quantlog_repo_path
from src.quantbuild.execution.quantlog_no_action import _CANONICAL_NO_ACTION

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "quantlog" / "minimal_day" / "quantbuild.jsonl"

_ENVELOPE_REQUIRED = {
    "event_id",
    "event_type",
    "event_version",
    "timestamp_utc",
    "ingested_at_utc",
    "source_system",
    "source_component",
    "environment",
    "run_id",
    "session_id",
    "source_seq",
    "trace_id",
    "severity",
    "payload",
}

_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _assert_non_empty_str(obj: dict, key: str) -> None:
    v = obj.get(key)
    assert isinstance(v, str) and v.strip(), f"{key} must be non-empty str"


def _validate_envelope(event: dict) -> None:
    missing = _ENVELOPE_REQUIRED - set(event.keys())
    assert not missing, f"missing envelope keys: {sorted(missing)}"
    for key in ("run_id", "session_id", "trace_id", "source_system", "source_component", "severity"):
        _assert_non_empty_str(event, key)
    assert event["source_system"] == "quantbuild"
    assert isinstance(event["source_seq"], int) and event["source_seq"] >= 1
    assert isinstance(event["payload"], dict)
    try:
        UUID(str(event["event_id"]))
    except ValueError as e:
        raise AssertionError(f"invalid event_id UUID: {event['event_id']!r}") from e
    for ts_key in ("timestamp_utc", "ingested_at_utc"):
        ts = event[ts_key]
        assert isinstance(ts, str) and _TS_RE.match(ts), f"bad {ts_key}: {ts!r}"


def _validate_payload(event_type: str, payload: dict) -> None:
    if event_type == "signal_evaluated":
        for k in ("signal_type", "signal_direction", "confidence"):
            assert k in payload, f"signal_evaluated missing {k}"
    elif event_type == "trade_action":
        assert "decision" in payload and "reason" in payload
        dec = str(payload["decision"]).upper()
        if dec == "NO_ACTION":
            reason = payload["reason"]
            assert isinstance(reason, str) and reason in _CANONICAL_NO_ACTION, (
                f"NO_ACTION reason not canonical: {reason!r}"
            )


def test_minimal_fixture_jsonl_contract() -> None:
    assert _FIXTURE.is_file(), f"missing fixture {_FIXTURE}"
    lines = [ln for ln in _FIXTURE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    last_seq = 0
    stream_key: tuple[str, str, str, str] | None = None
    for line in lines:
        event = json.loads(line)
        _validate_envelope(event)
        _validate_payload(str(event["event_type"]), event["payload"])
        seq = int(event["source_seq"])
        assert seq > last_seq
        last_seq = seq
        sk = (
            str(event["source_system"]),
            str(event["source_component"]),
            str(event["run_id"]),
            str(event["session_id"]),
        )
        if stream_key is None:
            stream_key = sk
        assert sk == stream_key, "fixture must be single emitter stream"


def test_quantlog_emitter_matches_contract(tmp_path) -> None:
    base = tmp_path / "qe"
    emitter = QuantLogEmitter(
        base_path=base,
        source_component="live_runner",
        environment="dry_run",
        run_id="run_emit_test",
        session_id="sess_emit_test",
    )
    ts = "2026-06-02T10:00:00Z"
    ev = emitter.emit(
        event_type="trade_action",
        trace_id="trace_emit_1",
        account_id="acct1",
        strategy_id="sqe_live_runner",
        symbol="XAUUSD",
        payload={"decision": "NO_ACTION", "reason": "no_setup"},
        timestamp_utc=ts,
    )
    _validate_envelope(ev)
    _validate_payload("trade_action", ev["payload"])
    written = (base / "2026-06-02" / "quantbuild.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(written.splitlines()[0])["run_id"] == "run_emit_test"


def test_check_quantlog_linkage_script() -> None:
    root = quantbuild_project_root()
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "check_quantlog_linkage.py")],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    if resolve_quantlog_repo_path() is None:
        assert proc.returncode == 0, out
        assert "WARNING" in out, out
    else:
        assert proc.returncode == 0, out
