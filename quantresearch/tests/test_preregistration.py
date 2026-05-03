from pathlib import Path

from quantresearch.paths import repo_root
from quantresearch.preregistration import (
    load_preregistration,
    validate_preregistration_v1,
    validate_temporal_integrity,
)


def test_hyp002_preregistration_file_validates_with_pipeline_run_time():
    p = repo_root() / "pipelines" / "hyp002_preregistration.json"
    data = load_preregistration(p)
    # Simulated bundle time before locked_at_utc (May 4) — retrospective, valid false
    assert validate_preregistration_v1(data, run_start_utc="2026-05-03T18:42:39.640992Z") == []


def test_validate_temporal_integrity_true_when_lock_before_run():
    prereg = {
        "locked_at_utc": "2026-05-01T10:00:00Z",
    }
    assert validate_temporal_integrity(prereg, "2026-05-03T12:00:00Z") is True


def test_validate_temporal_integrity_false_when_lock_after_run():
    prereg = {
        "locked_at_utc": "2026-05-04T10:00:00Z",
    }
    assert validate_temporal_integrity(prereg, "2026-05-03T12:00:00Z") is False


def test_validate_temporal_integrity_strict_lock_must_be_before_run_not_equal():
    """Same-second / equal timestamps: strict `<` — not `<=` (pipeline realism)."""
    ts = "2026-05-03T12:00:00.000000Z"
    prereg = {"locked_at_utc": ts}
    assert validate_temporal_integrity(prereg, ts) is False


def test_retrospective_valid_false_lock_after_run_passes_hyp002_shape():
    """HYP-002: retrospective + valid false + lock after run => no inconsistency error."""
    d = {
        "version": 1,
        "hypothesis_id": "HYP-002",
        "pre_registration_timestamp_utc": "2026-05-03T12:00:00Z",
        "pre_registration_status": "retrospective_reconstruction",
        "pre_registration_valid": False,
        "note": "retrospective filing after run.",
        "null_hypothesis_H0": "h0",
        "alternative_hypothesis_H1": "h1",
        "alpha": 0.05,
        "minimum_n": 300,
        "minimum_effect_size_r": 0.028,
        "test_plan_summary": "t",
        "locked_at_utc": "2026-05-04T10:00:00Z",
    }
    assert validate_preregistration_v1(d, run_start_utc="2026-05-03T18:42:39Z") == []


def test_valid_true_requires_lock_before_run():
    d = {
        "version": 1,
        "hypothesis_id": "X",
        "pre_registration_timestamp_utc": "2026-05-01T00:00:00Z",
        "pre_registration_status": "locked_before_run",
        "pre_registration_valid": True,
        "note": "n",
        "null_hypothesis_H0": "h0",
        "alternative_hypothesis_H1": "h1",
        "alpha": 0.05,
        "minimum_n": 30,
        "minimum_effect_size_r": 0.01,
        "test_plan_summary": "t",
        "locked_at_utc": "2026-05-04T10:00:00Z",
    }
    errs = validate_preregistration_v1(d, run_start_utc="2026-05-03T12:00:00Z")
    assert any("temporal integrity failed" in e for e in errs)


def test_valid_true_retrospective_rejected():
    d = {
        "version": 1,
        "hypothesis_id": "X",
        "pre_registration_timestamp_utc": "2026-05-01T00:00:00Z",
        "pre_registration_status": "retrospective_reconstruction",
        "pre_registration_valid": True,
        "note": "n",
        "null_hypothesis_H0": "h0",
        "alternative_hypothesis_H1": "h1",
        "alpha": 0.05,
        "minimum_n": 30,
        "minimum_effect_size_r": 0.01,
        "test_plan_summary": "t",
        "locked_at_utc": "2026-05-01T10:00:00Z",
    }
    errs = validate_preregistration_v1(d, run_start_utc="2026-05-03T12:00:00Z")
    assert any("incompatible with retrospective" in e for e in errs)


def test_locked_before_run_valid_passes():
    d = {
        "version": 1,
        "hypothesis_id": "X",
        "pre_registration_timestamp_utc": "2026-05-01T00:00:00Z",
        "pre_registration_status": "locked_before_run",
        "pre_registration_valid": True,
        "note": "n",
        "null_hypothesis_H0": "h0",
        "alternative_hypothesis_H1": "h1",
        "alpha": 0.05,
        "minimum_n": 30,
        "minimum_effect_size_r": 0.01,
        "test_plan_summary": "t",
        "locked_at_utc": "2026-05-01T10:00:00Z",
    }
    assert validate_preregistration_v1(d, run_start_utc="2026-05-03T12:00:00Z") == []


def test_retrospective_but_lock_before_run_inconsistent():
    d = {
        "version": 1,
        "hypothesis_id": "X",
        "pre_registration_timestamp_utc": "2026-05-01T00:00:00Z",
        "pre_registration_status": "retrospective_reconstruction",
        "pre_registration_valid": False,
        "note": "n",
        "null_hypothesis_H0": "h0",
        "alternative_hypothesis_H1": "h1",
        "alpha": 0.05,
        "minimum_n": 30,
        "minimum_effect_size_r": 0.01,
        "test_plan_summary": "t",
        "locked_at_utc": "2026-05-01T10:00:00Z",
    }
    errs = validate_preregistration_v1(d, run_start_utc="2026-05-03T12:00:00Z")
    assert any("inconsistent" in e for e in errs)
