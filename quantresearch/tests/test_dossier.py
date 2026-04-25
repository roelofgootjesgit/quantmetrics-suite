from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantresearch.dossier import render_experiment_dossier_md, write_experiment_dossier


def test_render_dossier_contains_governance_and_compare_rows():
    md, warns = render_experiment_dossier_md("EXP-2021-2025-throughput-discovery-v1")
    assert "WATCHLIST" in md
    assert "RELAX_CANDIDATE" in md
    assert "QuantOS promotion gate" in md
    assert "EXP-2021-2025-throughput-discovery-v1" in md
    assert "a0_baseline" in md
    assert "## 9. Edge verdicts" in md
    assert "edge_verdict" in md


def test_render_dossier_warns_when_links_missing(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-DOSSIER-NOLINK"
    d = exp_root / eid
    d.mkdir()
    (d / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (d / "experiment_plan.md").write_text("# P\n", encoding="utf-8")
    (d / "decision.md").write_text("# D\n\n## Final Decision\n\nX\n", encoding="utf-8")
    (d / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "custom",
                "hypothesis_summary": "s",
                "primary_metric": "expectancy_R",
                "secondary_metrics": ["pf"],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "suite": {"suite_root": str(tmp_path)},
            }
        ),
        encoding="utf-8",
    )
    md, warns = render_experiment_dossier_md(eid)
    assert any("links.json" in w.lower() for w in warns)
    assert "No `links.json`" in md or "links.json" in md


def test_write_experiment_dossier_writes_file(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-DOSSIER-WRITE"
    d = exp_root / eid
    d.mkdir()
    (d / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (d / "experiment_plan.md").write_text("# P\n", encoding="utf-8")
    (d / "decision.md").write_text("# D\n", encoding="utf-8")
    (d / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "custom",
                "hypothesis_summary": "s",
                "primary_metric": "expectancy_R",
                "secondary_metrics": ["pf"],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "suite": {"suite_root": str(tmp_path)},
            }
        ),
        encoding="utf-8",
    )
    out = write_experiment_dossier(eid)
    assert out.name == "EXPERIMENT_DOSSIER.md"
    assert "Experiment dossier" in out.read_text(encoding="utf-8")


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "experiments" / "EXP-2021-2025-throughput-discovery-v1").is_dir(),
    reason="experiment folder not present",
)
def test_write_dossier_idempotent_on_repo_experiment():
    out = write_experiment_dossier("EXP-2021-2025-throughput-discovery-v1")
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "discovery_rule_summary" in body
