"""Export JSONL / ZIP / CSV for ops (handbook §7.4)."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any

from quantlog.events.io import discover_jsonl_files


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
