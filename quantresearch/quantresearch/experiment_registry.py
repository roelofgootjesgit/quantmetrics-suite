"""Experiment registry: single source of truth for research experiments."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from quantresearch.paths import registry_dir

_EXPERIMENTS_FILE = "experiments.json"


def experiments_path(root: Path | None = None) -> Path:
    base = registry_dir() if root is None else root
    return base / _EXPERIMENTS_FILE


def load_registry(path: Path | None = None) -> dict[str, Any]:
    p = path or experiments_path()
    if not p.is_file():
        return {"version": 1, "experiments": []}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if "experiments" not in data:
        data["experiments"] = []
    return data


def save_registry(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or experiments_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def list_experiments(path: Path | None = None) -> list[dict[str, Any]]:
    return list(load_registry(path)["experiments"])


def get_experiment(experiment_id: str, path: Path | None = None) -> dict[str, Any] | None:
    for exp in list_experiments(path):
        if exp.get("experiment_id") == experiment_id:
            return exp
    return None


def _next_id(existing: list[dict[str, Any]]) -> str:
    max_n = 0
    for exp in existing:
        m = re.match(r"^EXP-(\d+)$", str(exp.get("experiment_id", "")))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"EXP-{max_n + 1:03d}"


def upsert_experiment(record: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Insert or replace by experiment_id; assigns EXP-XXX if experiment_id missing."""
    data = load_registry(path)
    experiments: list[dict[str, Any]] = data["experiments"]
    exp_id = record.get("experiment_id")
    if not exp_id:
        record = {**record, "experiment_id": _next_id(experiments)}
        exp_id = record["experiment_id"]

    replaced = False
    out: list[dict[str, Any]] = []
    for exp in experiments:
        if exp.get("experiment_id") == exp_id:
            out.append({**exp, **record, "experiment_id": exp_id})
            replaced = True
        else:
            out.append(exp)
    if not replaced:
        out.append({**record, "experiment_id": exp_id})

    data["experiments"] = out
    save_registry(data, path)
    return get_experiment(exp_id, path) or record


def delete_experiment(experiment_id: str, path: Path | None = None) -> bool:
    data = load_registry(path)
    before = len(data["experiments"])
    data["experiments"] = [e for e in data["experiments"] if e.get("experiment_id") != experiment_id]
    if len(data["experiments"]) == before:
        return False
    save_registry(data, path)
    return True
