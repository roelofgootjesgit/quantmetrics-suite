"""Tests for per-trade R inference (synthetic and edge cases)."""

from __future__ import annotations

import numpy as np
import pytest

import quantmetrics_analytics.analysis.inference_engine as inference_mod
from quantmetrics_analytics.analysis.inference_engine import run_inference
from quantmetrics_analytics.analysis.inference_report import write_inference_report
from quantmetrics_analytics.analysis.r_series_input import (
    extract_trade_closed_pnl_r,
    load_r_series_from_inputs,
    resolve_inference_run_id,
)


def test_insufficient_n_skips_hypothesis_test():
    r = [0.01] * 50
    out = run_inference(r, minimum_n=300)
    assert out.statistical_verdict == "INSUFFICIENT_N"
    assert out.test_used == "none"
    assert out.p_value is None
    assert out.economic_verdict == "PENDING"


def test_wilcoxon_path_small_positive_shift():
    rng = np.random.default_rng(0)
    r = (rng.standard_normal(400) * 0.4 + 0.08).tolist()
    out = run_inference(r, minimum_n=300, minimum_effect_size_r=0.0, bootstrap_iterations=2000)
    assert out.n == 400
    assert out.test_used in ("wilcoxon_signed_rank", "one_sample_t")
    assert out.p_value is not None
    assert out.statistical_verdict in ("PASS", "FAIL")


def test_resolve_run_id_single():
    events = [
        {"event_type": "trade_closed", "run_id": "run_a", "payload": {"pnl_r": 0.1}},
        {"event_type": "trade_closed", "run_id": "run_a", "payload": {"pnl_r": -0.05}},
    ]
    assert resolve_inference_run_id(events, None) == "run_a"


def test_extract_trade_closed_pnl_r_filtered():
    events = [
        {"event_type": "trade_closed", "run_id": "a", "payload": {"pnl_r": 1.0}},
        {"event_type": "trade_closed", "run_id": "b", "payload": {"pnl_r": 2.0}},
    ]
    assert extract_trade_closed_pnl_r(events, "a") == [1.0]


def test_load_r_series_fallback(tmp_path):
    run_id = "qb_test_fallback"
    jsonl = tmp_path / f"{run_id}.jsonl"
    jsonl.write_text("", encoding="utf-8")
    sidecar = tmp_path / f"{run_id}_trade_r_series.json"
    sidecar.write_text(
        '{"schema_version":"trade_r_series_v1","run_id":"qb_test_fallback","trades":['
        '{"pnl_r":0.5},{"pnl_r":-0.25}]}',
        encoding="utf-8",
    )
    events: list = []
    r, src = load_r_series_from_inputs(events, run_id=run_id, jsonl_paths=[jsonl])
    assert src == "trade_r_series_json"
    assert r == [0.5, -0.25]


def test_economic_verdict_uses_ci_lower_not_point_mean(monkeypatch):
    """High sample mean but CI lower below floor → economic FAIL."""

    def _fixed_ci(_arr, _n_resamples, _seed):
        return 0.011, 0.09, "bootstrap_percentile"

    monkeypatch.setattr(inference_mod, "_bootstrap_ci_mean", _fixed_ci)
    rng = np.random.default_rng(3)
    r = (rng.standard_normal(400) * 0.12 + 0.06).tolist()
    out = inference_mod.run_inference(r, minimum_n=300, minimum_effect_size_r=0.028, bootstrap_iterations=100)
    assert out.mean_r > 0.028
    assert out.economic_verdict == "FAIL"


def test_write_inference_report_json_roundtrip(tmp_path):
    rng = np.random.default_rng(1)
    r = (rng.standard_normal(320) * 0.2 + 0.05).tolist()
    out = run_inference(r, minimum_n=300, bootstrap_iterations=800)
    p = write_inference_report(
        out,
        run_id="r1",
        experiment_id="EXP-UNIT",
        output_dir=tmp_path,
        r_source="trade_closed_jsonl",
    )
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "inference_v1" in text
    assert "verdict" in text
