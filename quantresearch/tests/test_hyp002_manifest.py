"""HYP-002 promotion bundle manifest is valid JSON with expected keys."""

from __future__ import annotations

import json
from pathlib import Path

from quantresearch.paths import repo_root


def test_hyp002_promotion_bundle_manifest():
    p = repo_root() / "pipelines" / "hyp002_promotion_bundle.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("hypothesis_id") == "HYP-002"
    runs = data.get("runs", [])
    assert len(runs) >= 3
    ids = {r["id"] for r in runs}
    assert "v5a_expblk_5y_spread05" in ids
    assert all("config_file" in r for r in runs)
