"""Export JSONL / ZIP / CSV for ops (handbook §7.4)."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files, iter_jsonl_file


def read_jsonl_text(paths: list[Path]) -> str:
    """Concatenate raw JSONL lines (preserves order: sorted paths, file line order)."""
    chunks: list[str] = []
    for fp in sorted(paths, key=lambda p: str(p)):
        if fp.is_file():
            chunks.append(fp.read_text(encoding="utf-8"))
    return "".join(chunks)


def zip_run_files(file_paths: list[Path]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(set(file_paths), key=lambda p: str(p)):
            if fp.is_file():
                zf.write(fp, arcname=fp.name)
    return buf.getvalue()


def zip_day_directory(day_path: Path) -> bytes:
    day_path = day_path.expanduser().resolve()
    paths = [Path(p) for p in discover_jsonl_files(day_path)]
    return zip_run_files(paths)


def normalized_export_time_bounds(rows: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    """Min/max ``timestamp_utc`` among exported rows (ISO UTC; lexicographic order is valid)."""
    ts: list[str] = []
    for r in rows:
        t = str(r.get("timestamp_utc") or "").strip()
        if t:
            ts.append(t)
    if not ts:
        return None, None
    return min(ts), max(ts)


def jsonl_shard_timestamp_bounds(shard_path: Path) -> tuple[str | None, str | None]:
    """Min/max ``timestamp_utc`` among successfully parsed lines in one JSONL file."""
    fp = Path(shard_path).expanduser().resolve()
    min_ts: str | None = None
    max_ts: str | None = None
    if not fp.is_file():
        return None, None
    for raw in iter_jsonl_file(fp):
        if raw.parsed is None:
            continue
        ts = raw.parsed.get("timestamp_utc")
        if not isinstance(ts, str) or not ts.strip():
            continue
        ts = ts.strip()
        if min_ts is None or ts < min_ts:
            min_ts = ts
        if max_ts is None or ts > max_ts:
            max_ts = ts
    return min_ts, max_ts


def normalized_rows_csv(rows: list[dict[str, Any]]) -> str:
    """CSV of flat ops columns (exclude ``_raw``)."""
    cols = [
        "timestamp_utc",
        "run_id",
        "event_type",
        "symbol",
        "session",
        "regime",
        "decision",
        "reason_code",
        "confidence",
        "source_system",
        "order_ref",
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k, "") for k in cols})
    return out.getvalue()
