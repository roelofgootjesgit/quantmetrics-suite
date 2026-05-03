"""Serialize :class:`InferenceResult` to ``inference_v1`` JSON."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from quantmetrics_analytics.analysis.inference_engine import InferenceResult, run_inference
from quantmetrics_analytics.analysis.r_series_input import load_r_series_from_inputs, resolve_inference_run_id

PrecisionTier = Literal["standard", "high"]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_inference_report(
    result: InferenceResult,
    *,
    run_id: str,
    experiment_id: str,
    output_dir: Path,
    precision_tier: PrecisionTier = "standard",
    r_source: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": "inference_v1",
        "generated_at_utc": utcnow_iso(),
        "run_id": run_id,
        "experiment_id": experiment_id,
        "bootstrap_precision_tier": precision_tier,
        "r_source": r_source,
        "sample": {
            "n": result.n,
            "mean_r": result.mean_r,
            "std_r": result.std_r,
            "median_r": result.median_r,
        },
        "normality": {
            "shapiro_wilk_p": result.shapiro_wilk_p,
            "note": "Shapiro-Wilk only for 3 <= n <= 5000; null above 5000.",
        },
        "hypothesis_test": {
            "test_used": result.test_used,
            "h0_median_r": 0.0,
            "p_value": result.p_value,
            "alpha": result.alpha_used,
            "significant_at_alpha": result.significant_at_alpha,
        },
        "confidence_interval": {
            "method": result.ci_method,
            "level": 0.95,
            "bootstrap_iterations": result.bootstrap_iterations,
            "bootstrap_seed": result.bootstrap_seed,
        },
        "effect_size": {
            "cohens_d": result.cohens_d,
            "interpretation": result.effect_interpretation,
        },
        "verdict": {
            "statistical_significance": result.statistical_verdict,
            "economic_significance": result.economic_verdict,
            "minimum_effect_size_used": result.minimum_effect_size_used,
            "economic_rule": "ci_95_lower >= minimum_effect_size_r",
        },
    }
    def _num(x: float | None) -> float | None:
        if x is None:
            return None
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return float(x)

    lo = _num(result.ci_95_lower)
    hi = _num(result.ci_95_upper)
    report["confidence_interval"]["lower"] = lo
    report["confidence_interval"]["upper"] = hi
    # Aliases for readers / governance code that expect explicit CI field names.
    report["confidence_interval"]["ci_95_lower"] = lo
    report["confidence_interval"]["ci_95_upper"] = hi

    path = output_dir / f"{run_id}_inference_report.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return path


def run_inference_for_events(
    events: list[dict[str, Any]],
    jsonl_paths: list[Path],
    *,
    run_id_explicit: str | None,
    experiment_id: str,
    output_dir: Path,
    precision_tier: str,
    alpha: float,
    minimum_n: int,
    minimum_effect_size_r: float,
    require_jsonl_trade_closed: bool,
) -> tuple[Path, InferenceResult, str]:
    run_id = resolve_inference_run_id(events, run_id_explicit)
    r_series, r_source = load_r_series_from_inputs(events, run_id=run_id, jsonl_paths=jsonl_paths)
    if not r_series:
        raise ValueError("No per-trade R values found (trade_closed.pnl_r or trade_r_series.json).")
    if require_jsonl_trade_closed and r_source != "trade_closed_jsonl":
        raise RuntimeError(
            "Strict QuantLog JSONL required (QUANTMETRICS_INFERENCE_REQUIRE_JSONL=1 or --inference-require-jsonl) "
            f"but R source was {r_source!r}."
        )
    tier = precision_tier if precision_tier in {"standard", "high"} else "standard"
    n_boot = 50_000 if tier == "high" else 10_000
    result = run_inference(
        r_series,
        alpha=alpha,
        minimum_n=minimum_n,
        minimum_effect_size_r=minimum_effect_size_r,
        bootstrap_iterations=n_boot,
        bootstrap_seed=42,
    )
    path = write_inference_report(
        result,
        run_id=run_id,
        experiment_id=experiment_id,
        output_dir=output_dir,
        precision_tier=tier,  # type: ignore[arg-type]
        r_source=r_source,
    )
    return path, result, r_source


def inference_require_jsonl_from_env() -> bool:
    v = os.environ.get("QUANTMETRICS_INFERENCE_REQUIRE_JSONL", "").strip().lower()
    return v in {"1", "true", "yes", "on"}
