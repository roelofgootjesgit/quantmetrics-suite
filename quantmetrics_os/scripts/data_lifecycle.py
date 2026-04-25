#!/usr/bin/env python3
"""V0 data lifecycle scanner for QuantMetrics OS.

Scope (V0 only):
- scan quantmetrics_os/runs/
- detect run folders (runs/<experiment>/<role>/)
- read status.json when present
- classify missing status.json as "unknown" (report-only, no file writes)
- calculate folder sizes
- print dry-run table
- write markdown/json reports

No deletion/compression/mutation is performed in V0.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RunScan:
    experiment: str
    role: str
    path: str
    bytes_total: int
    status: str
    status_source: str
    run_id: str
    delete_allowed: bool
    notes: str


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _discover_qmos_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _folder_size_bytes(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


def _human_bytes(value: int) -> str:
    num = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = units[0]
    for unit in units:
        if num < 1024.0 or unit == units[-1]:
            break
        num /= 1024.0
    return f"{num:.2f} {unit}"


def _extract_run_id(run_dir: Path, status_payload: dict[str, Any] | None) -> str:
    if status_payload:
        run_id = str(status_payload.get("run_id", "")).strip()
        if run_id:
            return run_id
    run_info = _safe_read_json(run_dir / "run_info.json")
    if run_info:
        run_id = str(run_info.get("run_id", "")).strip()
        if run_id:
            return run_id
    return ""


def _scan_runs(runs_root: Path, qmos_root: Path) -> list[RunScan]:
    rows: list[RunScan] = []
    if not runs_root.is_dir():
        return rows

    for experiment_dir in sorted([p for p in runs_root.iterdir() if p.is_dir()]):
        for role_dir in sorted([p for p in experiment_dir.iterdir() if p.is_dir()]):
            status_path = role_dir / "status.json"
            status_payload = _safe_read_json(status_path)
            status_source = "status.json"
            notes = ""

            if status_payload is None:
                status = "unknown"
                status_source = "inferred_missing_status"
                delete_allowed = False
                notes = "missing status.json; manual classification required"
            else:
                status = str(status_payload.get("status", "unknown")).strip() or "unknown"
                delete_allowed = bool(status_payload.get("delete_allowed", False))
                if status == "unknown":
                    notes = "status.json present but unresolved classification"

            rows.append(
                RunScan(
                    experiment=experiment_dir.name,
                    role=role_dir.name,
                    path=str(role_dir.resolve().relative_to(qmos_root.resolve())).replace("\\", "/"),
                    bytes_total=_folder_size_bytes(role_dir),
                    status=status,
                    status_source=status_source,
                    run_id=_extract_run_id(role_dir, status_payload),
                    delete_allowed=delete_allowed,
                    notes=notes,
                )
            )
    return rows


def _markdown_report(items: list[RunScan], generated_at_utc: str) -> str:
    total_bytes = sum(item.bytes_total for item in items)
    unknown_count = sum(1 for item in items if item.status == "unknown")
    lines: list[str] = [
        "# Data Lifecycle Report (V0 Dry Run)",
        "",
        f"- Generated (UTC): `{generated_at_utc}`",
        f"- Runs scanned: `{len(items)}`",
        f"- Unknown status runs: `{unknown_count}`",
        f"- Total size: `{_human_bytes(total_bytes)}` ({total_bytes} bytes)",
        "- Actions: `none` (V0 does not delete/compress/mutate)",
        "",
        "## Run table",
        "",
        "| Experiment | Role | Run ID | Status | Delete allowed | Size | Path | Notes |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for item in items:
        lines.append(
            "| "
            f"{item.experiment} | "
            f"{item.role} | "
            f"{item.run_id or '-'} | "
            f"{item.status} | "
            f"{item.delete_allowed} | "
            f"{_human_bytes(item.bytes_total)} | "
            f"`{item.path}` | "
            f"{item.notes or '-'} |"
        )
    lines.extend(
        [
            "",
            "## Guardrails (enforced in V0)",
            "",
            "- No deletion",
            "- No compression",
            "- No archive writes",
            "- No status mutation (missing `status.json` is reported as `unknown` only)",
            "",
        ]
    )
    return "\n".join(lines)


def _print_table(items: list[RunScan]) -> None:
    header = "experiment | role | run_id | status | delete_allowed | size | path"
    print(header)
    print("-" * len(header))
    for item in items:
        print(
            f"{item.experiment} | {item.role} | {item.run_id or '-'} | "
            f"{item.status} | {item.delete_allowed} | {_human_bytes(item.bytes_total)} | {item.path}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuantMetrics data lifecycle scanner (V0)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (default behavior in V0).",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Write markdown/json report files (enabled by default in V0).",
    )
    return parser


def main() -> int:
    _ = _build_parser().parse_args()
    qmos_root = _discover_qmos_root()
    runs_root = qmos_root / "runs"
    reports_dir = qmos_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    generated_at_utc = _now_utc_iso()
    items = _scan_runs(runs_root=runs_root, qmos_root=qmos_root)
    _print_table(items)

    report_json = {
        "generated_at_utc": generated_at_utc,
        "version": "v0",
        "mode": "dry_run",
        "actions_performed": [],
        "runs_scanned": len(items),
        "unknown_status_runs": sum(1 for item in items if item.status == "unknown"),
        "total_bytes": sum(item.bytes_total for item in items),
        "runs": [asdict(item) for item in items],
    }

    json_path = reports_dir / "data_lifecycle_report.json"
    md_path = reports_dir / "data_lifecycle_report.md"
    json_path.write_text(json.dumps(report_json, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown_report(items, generated_at_utc), encoding="utf-8")

    print("")
    print(f"wrote: {json_path}")
    print(f"wrote: {md_path}")
    print("V0 complete: no delete/compress actions executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
