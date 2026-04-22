"""Confirmed edges, rejected hypotheses, and structured edge registry."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quantresearch.paths import registry_dir

_CONFIRMED = "confirmed_edges.json"
_REJECTED = "rejected_hypotheses.json"


def _confirmed_path(root: Path | None = None) -> Path:
    return (root or registry_dir()) / _CONFIRMED


def _rejected_path(root: Path | None = None) -> Path:
    return (root or registry_dir()) / _REJECTED


def load_confirmed(path: Path | None = None) -> dict[str, Any]:
    p = _confirmed_path(path)
    if not p.is_file():
        return {"version": 1, "edges": []}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if "edges" not in data:
        data["edges"] = []
    return data


def save_confirmed(data: dict[str, Any], path: Path | None = None) -> None:
    p = _confirmed_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def load_rejected(path: Path | None = None) -> dict[str, Any]:
    p = _rejected_path(path)
    if not p.is_file():
        return {"version": 1, "rejected": []}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if "rejected" not in data:
        data["rejected"] = []
    return data


def save_rejected(data: dict[str, Any], path: Path | None = None) -> None:
    p = _rejected_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _next_id(prefix: str, items: list[dict[str, Any]], id_key: str = "id") -> str:
    max_n = 0
    pat = prefix + r"-(\d+)$"
    import re

    for item in items:
        m = re.match(pat, str(item.get(id_key, "")))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}-{max_n + 1:03d}"


def add_edge_record(record: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Append a full edge registry record (regime/session/setup/...); assigns id if missing."""
    data = load_confirmed(path)
    edges: list[dict[str, Any]] = data["edges"]
    rec = dict(record)
    if not rec.get("id"):
        rec["id"] = _next_id("EDGE", edges)
    # replace if same id
    others = [e for e in edges if e.get("id") != rec["id"]]
    others.append(rec)
    data["edges"] = others
    save_confirmed(data, path)
    return rec


def add_rejected_hypothesis(record: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    data = load_rejected(path)
    rej: list[dict[str, Any]] = data["rejected"]
    rec = dict(record)
    if not rec.get("id"):
        rec["id"] = _next_id("REJ", rej)
    others = [e for e in rej if e.get("id") != rec["id"]]
    others.append(rec)
    data["rejected"] = others
    save_rejected(data, path)
    return rec
