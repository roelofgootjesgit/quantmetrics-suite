from __future__ import annotations

import json
from pathlib import Path

from quantresearch.ledger import (
    load_experiment,
    mark_experiment_completed,
    validate_experiment,
    write_research_ledger_md,
)


def test_validate_throughput_discovery_experiment():
    eid = "EXP-2021-2025-throughput-discovery-v1"
    errs = validate_experiment(eid)
    assert errs == [], errs


def test_validate_session_watchlist_experiment():
    eid = "EXP-2021-2025-session-relax-watchlist-v1"
    errs = validate_experiment(eid)
    assert errs == [], errs


def test_pre_run_accepts_planned_without_post_run_artifacts(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-PRE-RUN-TEST"
    exp_dir = exp_root / eid
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "run_matrix",
            }
        ),
        encoding="utf-8",
    )
    assert validate_experiment(eid, mode="pre_run") == []


def test_pre_run_rejects_planned_with_links_json(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-LINKS-BLOCK"
    exp_dir = exp_root / eid
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (exp_dir / "links.json").write_text('{"quantos_run_dir": "x"}', encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    errs = validate_experiment(eid, mode="pre_run")
    assert errs and any("links.json" in e for e in errs)


def test_pre_run_rejects_planned_with_stale_completed_at(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-STALE-CAT"
    exp_dir = exp_root / eid
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-04-01T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    errs = validate_experiment(eid, mode="pre_run")
    assert errs and any("completed_at_utc" in e for e in errs)


def test_pre_run_accepts_child_with_rerun_lineage(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    parent_id = "EXP-PARENT-V1"
    child_id = "EXP-CHILD-V2"
    pdir = exp_root / parent_id
    pdir.mkdir(parents=True)
    (pdir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (pdir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (pdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": parent_id,
                "title": "parent",
                "status": "completed",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-04-20T10:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    cdir = exp_root / child_id
    cdir.mkdir(parents=True)
    (cdir / "hypothesis.md").write_text("# H2\n", encoding="utf-8")
    (cdir / "experiment_plan.md").write_text("# Plan2\n", encoding="utf-8")
    (cdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": child_id,
                "title": "child",
                "status": "planned",
                "created_at_utc": "2026-04-21T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "y",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "parent_experiment_id": parent_id,
                "rerun_reason": "Re-sample with extended window after v1 watchlist outcome.",
                "rerun_index": 1,
                "previous_completed_at_utc": "2026-04-20T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    assert validate_experiment(child_id, mode="pre_run") == []


def test_pre_run_rejects_missing_rerun_reason(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    parent_id = "EXP-PARENT-NOREASON"
    child_id = "EXP-CHILD-NOREASON"
    pdir = exp_root / parent_id
    pdir.mkdir(parents=True)
    (pdir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (pdir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (pdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": parent_id,
                "title": "parent",
                "status": "completed",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-04-20T10:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    cdir = exp_root / child_id
    cdir.mkdir(parents=True)
    (cdir / "hypothesis.md").write_text("# H2\n", encoding="utf-8")
    (cdir / "experiment_plan.md").write_text("# Plan2\n", encoding="utf-8")
    (cdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": child_id,
                "title": "child",
                "status": "planned",
                "created_at_utc": "2026-04-21T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "y",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "parent_experiment_id": parent_id,
                "rerun_reason": "   ",
                "rerun_index": 1,
                "previous_completed_at_utc": "2026-04-20T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    errs = validate_experiment(child_id, mode="pre_run")
    assert errs and any("rerun_reason" in e for e in errs)


def test_pre_run_accepts_previous_completed_with_z_suffix(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    parent_id = "EXP-PARENT-Z"
    child_id = "EXP-CHILD-Z"
    pdir = exp_root / parent_id
    pdir.mkdir(parents=True)
    (pdir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (pdir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (pdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": parent_id,
                "title": "parent",
                "status": "completed",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-04-20T10:00:00+00:00",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    cdir = exp_root / child_id
    cdir.mkdir(parents=True)
    (cdir / "hypothesis.md").write_text("# H2\n", encoding="utf-8")
    (cdir / "experiment_plan.md").write_text("# Plan2\n", encoding="utf-8")
    (cdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": child_id,
                "title": "child",
                "status": "planned",
                "created_at_utc": "2026-04-21T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "y",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "parent_experiment_id": parent_id,
                "rerun_reason": "ISO format equivalence",
                "rerun_index": 1,
                "previous_completed_at_utc": "2026-04-20T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    assert validate_experiment(child_id, mode="pre_run") == []


def test_pre_run_rejects_self_parent(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-SELF-PARENT"
    exp_dir = exp_root / eid
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "parent_experiment_id": eid,
                "rerun_reason": "bad",
                "rerun_index": 1,
                "previous_completed_at_utc": "2026-04-20T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    errs = validate_experiment(eid, mode="pre_run")
    assert errs and any("self-reference" in e.lower() or "different experiment" in e.lower() for e in errs)


def test_pre_run_rejects_wrong_previous_completed_at(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    parent_id = "EXP-PARENT-MISMATCH"
    child_id = "EXP-CHILD-MISMATCH"
    pdir = exp_root / parent_id
    pdir.mkdir(parents=True)
    (pdir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (pdir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (pdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": parent_id,
                "title": "parent",
                "status": "completed",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "completed_at_utc": "2026-04-20T10:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    cdir = exp_root / child_id
    cdir.mkdir(parents=True)
    (cdir / "hypothesis.md").write_text("# H2\n", encoding="utf-8")
    (cdir / "experiment_plan.md").write_text("# Plan2\n", encoding="utf-8")
    (cdir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": child_id,
                "title": "child",
                "status": "planned",
                "created_at_utc": "2026-04-21T00:00:00Z",
                "matrix_type": "throughput-discovery",
                "hypothesis_summary": "y",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "parent_experiment_id": parent_id,
                "rerun_reason": "wrong timestamp",
                "rerun_index": 1,
                "previous_completed_at_utc": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    errs = validate_experiment(child_id, mode="pre_run")
    assert errs and any("previous_completed_at_utc" in e for e in errs)


def test_pre_run_rejects_completed_status(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-COMPLETED-BLOCK"
    exp_dir = exp_root / eid
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "completed",
                "created_at_utc": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    errs = validate_experiment(eid, mode="pre_run")
    assert errs and any("planned" in e.lower() or "running" in e.lower() for e in errs)


def test_full_validate_planned_skips_final_decision_requirement(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-PLANNED-FULL"
    exp_dir = exp_root / eid
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (exp_dir / "decision.md").write_text("# Draft only\n", encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "custom",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    assert validate_experiment(eid, mode="full") == []


def test_mark_experiment_completed_updates_json(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    eid = "EXP-MARK-DONE"
    exp_dir = exp_root / eid
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "experiment_plan.md").write_text("# Plan\n", encoding="utf-8")
    (exp_dir / "decision.md").write_text("# D\n\n## Final Decision\n\nX\n", encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": eid,
                "title": "t",
                "status": "running",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "custom",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": [],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
            }
        ),
        encoding="utf-8",
    )
    mark_experiment_completed(eid, completed_at_utc="2026-04-25T12:00:00Z")
    exp = load_experiment(eid)
    assert exp["status"] == "completed"
    assert exp["completed_at_utc"] == "2026-04-25T12:00:00Z"


def test_research_ledger_md_writes(tmp_path, monkeypatch):
    exp_root = tmp_path / "experiments"
    monkeypatch.setattr("quantresearch.ledger.repo_root", lambda: tmp_path)
    monkeypatch.setattr("quantresearch.ledger.experiments_dir", lambda: exp_root)
    exp_root.mkdir()
    exp_dir = exp_root / "EXP-TEST-1"
    exp_dir.mkdir(parents=True)
    (exp_dir / "hypothesis.md").write_text("# H\n", encoding="utf-8")
    (exp_dir / "decision.md").write_text("# Decision\n\n## Final Decision\n\nUNKNOWN\n", encoding="utf-8")
    (exp_dir / "experiment.json").write_text(
        json.dumps(
            {
                "experiment_id": "EXP-TEST-1",
                "title": "t",
                "status": "planned",
                "created_at_utc": "2026-01-01T00:00:00Z",
                "matrix_type": "custom",
                "hypothesis_summary": "x",
                "primary_metric": "expectancy_R",
                "secondary_metrics": ["profit_factor"],
                "promotion_decision": "UNKNOWN",
                "discovery_tier": "none",
                "next_action": "none",
                "quantresearch_files": {
                    "hypothesis_md": "hypothesis.md",
                    "experiment_plan_md": "experiment_plan.md",
                    "results_summary_md": "results_summary.md",
                    "decision_md": "decision.md",
                    "links_json": "links.json",
                },
                "matrix_definition": {
                    "base_config": "c.yaml",
                    "start_date": "2021-01-01",
                    "end_date": "2021-12-31",
                    "variants": [{"key": "X", "description": "d"}],
                },
            }
        ),
        encoding="utf-8",
    )
    (exp_dir / "experiment_plan.md").write_text("# plan\n", encoding="utf-8")
    (exp_dir / "results_summary.md").write_text("# res\n", encoding="utf-8")
    (exp_dir / "links.json").write_text('{"quantos_run_dir": "quantmetrics_os/runs/missing"}', encoding="utf-8")
    out = write_research_ledger_md()
    assert out.is_file()
    body = out.read_text(encoding="utf-8")
    assert "EXP-TEST-1" in body
