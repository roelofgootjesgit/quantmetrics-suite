"""Pre-registration payload validation (v1) — structure + temporal integrity for true pre-reg."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_KEYS = (
    "version",
    "hypothesis_id",
    "pre_registration_timestamp_utc",
    "pre_registration_status",
    "pre_registration_valid",
    "note",
    "null_hypothesis_H0",
    "alternative_hypothesis_H1",
    "alpha",
    "minimum_n",
    "minimum_effect_size_r",
    "test_plan_summary",
)


def load_preregistration(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso_utc(s: str) -> datetime:
    t = str(s).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_temporal_integrity(prereg: dict[str, Any], run_start_utc: str) -> bool:
    """True iff locked_at_utc is strictly before run_start (both ISO-8601 UTC)."""
    locked = prereg.get("locked_at_utc")
    if locked is None or not str(locked).strip() or not str(run_start_utc).strip():
        return False
    try:
        return _parse_iso_utc(str(locked)) < _parse_iso_utc(str(run_start_utc))
    except ValueError:
        return False


def validate_preregistration_v1(
    data: dict[str, Any],
    *,
    run_start_utc: str | None = None,
) -> list[str]:
    """Return human-readable errors; empty list means OK for v1."""
    errs: list[str] = []
    for k in REQUIRED_KEYS:
        v = data.get(k)
        if v is None or (isinstance(v, str) and not str(v).strip()):
            errs.append(f"missing or empty field: {k}")
    if data.get("version") != 1:
        errs.append("version must be 1 for v1 schema")

    status = data.get("pre_registration_status")
    if status not in ("retrospective_reconstruction", "locked_before_run"):
        errs.append("pre_registration_status must be retrospective_reconstruction or locked_before_run")

    pv = data.get("pre_registration_valid")
    if not isinstance(pv, bool):
        errs.append("pre_registration_valid must be a boolean")

    try:
        a = float(data.get("alpha"))
        if not (0 < a <= 1):
            errs.append("alpha must be in (0, 1]")
    except (TypeError, ValueError):
        errs.append("alpha must be a number")
    try:
        n = int(data.get("minimum_n"))
        if n < 1:
            errs.append("minimum_n must be >= 1")
    except (TypeError, ValueError):
        errs.append("minimum_n must be an integer")

    if isinstance(pv, bool) and pv is True:
        if status == "retrospective_reconstruction":
            errs.append("pre_registration_valid true is incompatible with retrospective_reconstruction")
        if not data.get("locked_at_utc"):
            errs.append("locked_at_utc required when pre_registration_valid is true")
        if not run_start_utc or not str(run_start_utc).strip():
            errs.append("run_start_utc required when pre_registration_valid is true (for temporal integrity)")
        elif data.get("locked_at_utc") and not validate_temporal_integrity(data, str(run_start_utc)):
            errs.append("temporal integrity failed: locked_at_utc must be strictly before run_start_utc")

    if (
        isinstance(pv, bool)
        and pv is False
        and status == "retrospective_reconstruction"
        and data.get("locked_at_utc")
        and run_start_utc
        and str(run_start_utc).strip()
        and validate_temporal_integrity(data, str(run_start_utc))
    ):
        errs.append(
            "inconsistent: status is retrospective_reconstruction but locked_at_utc precedes run_start_utc "
            "(looks like a true pre-reg; fix status/valid or timestamps)"
        )

    return errs


def default_hyp002_preregistration_path() -> Path:
    from quantresearch.paths import repo_root

    return repo_root() / "pipelines" / "hyp002_preregistration.json"
