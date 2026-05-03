"""Load QuantAnalytics inference_report.json and map verdicts to ledger status fields."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from quantresearch.paths import experiments_dir


def load_inference_report(experiment_id: str, *, role: str = "single") -> dict[str, Any] | None:
    """Load ``inference_report.json`` from the experiment ledger folder.

    ``role`` is reserved for future QuantOS bundle paths; currently only the ledger file is used.
    """
    _ = role
    exp_dir = experiments_dir() / experiment_id.strip()
    p = exp_dir / "inference_report.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_inference_report_from_dir(exp_dir: Path) -> dict[str, Any] | None:
    """Load ``inference_report.json`` when the experiment directory is already known."""
    p = exp_dir / "inference_report.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _ci_lower_from_inference(inference: dict[str, Any]) -> float | None:
    ci = inference.get("confidence_interval")
    if not isinstance(ci, dict):
        return None
    raw = ci.get("lower")
    if raw is None:
        raw = ci.get("ci_95_lower")
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def apply_inference_to_experiment(
    experiment_id: str,
    prereg: dict[str, Any],
    inference: dict[str, Any],
) -> dict[str, Any]:
    """Compare inference JSON to pre-registration gates (no trading-metric recomputation).

    Economic gate uses the **lower bound of the 95% CI on mean R**, not the point mean.
    """
    _ = experiment_id
    verdict = inference.get("verdict") if isinstance(inference.get("verdict"), dict) else {}
    sample = inference.get("sample") if isinstance(inference.get("sample"), dict) else {}

    stat = str(verdict.get("statistical_significance", "")).strip().upper()
    try:
        n = int(sample.get("n", 0))
    except (TypeError, ValueError):
        n = 0
    min_n = int(prereg.get("minimum_n", 300))
    try:
        min_effect = float(prereg.get("minimum_effect_size_r", 0.028))
    except (TypeError, ValueError):
        min_effect = 0.028

    ci_lower = _ci_lower_from_inference(inference)
    econ_pass = ci_lower is not None and ci_lower >= min_effect

    if stat == "INSUFFICIENT_N" or n < min_n:
        return {
            "academic_status": "INSUFFICIENT_N",
            "effective_status": "GOVERNANCE_ONLY",
            "inference_reason": f"n={n} below minimum_n={min_n} or statistical verdict INSUFFICIENT_N",
        }
    if stat == "PASS" and econ_pass:
        return {"academic_status": "PASS", "effective_status": "PROMOTE_FULL"}
    reasons: list[str] = []
    if stat != "PASS":
        reasons.append(f"statistical_significance={stat}")
    if not econ_pass:
        if ci_lower is None:
            reasons.append("economic_gate=missing_or_invalid_ci_95_lower")
        else:
            reasons.append(f"economic_gate=ci_95_lower({ci_lower:.6f})<minimum_effect_size_r({min_effect})")
    return {
        "academic_status": "FAIL",
        "effective_status": "GOVERNANCE_ONLY",
        "inference_reason": "; ".join(reasons) if reasons else "inference_gates_not_met",
    }
