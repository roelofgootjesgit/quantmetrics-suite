from __future__ import annotations


def create_edge_verdict(
    guard_attribution: dict,
    stability: dict,
    decision_quality: list[dict],
    warnings: list[dict],
) -> dict:
    guard_rows = guard_attribution.get("guards", [])
    strong_guards = [g for g in guard_rows if g.get("verdict") == "EDGE_PROTECTIVE"]
    destructive_guards = [g for g in guard_rows if g.get("verdict") == "EDGE_DESTROYING"]

    quality_scores = [row.get("quality_score", 0) for row in decision_quality if row.get("quality_label") != "UNKNOWN"]
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
    total_quality = len(decision_quality)

    regime_rows = stability.get("regime", [])
    promising_regimes = [r for r in regime_rows if r.get("verdict") == "PROMISING"]
    unstable_regimes = [r for r in regime_rows if r.get("verdict") in {"UNSTABLE", "WEAK_OR_NEGATIVE"}]

    low_sample = any(
        row.get("sample_quality") in {"INSUFFICIENT_DATA", "WEAK_EVIDENCE"}
        for row in guard_rows
    )

    if low_sample:
        edge_verdict = "VALIDATION_REQUIRED"
        confidence = "LOW"
        main_risk = "Sample size too small to justify promotion"
        recommended = "Increase representative sample size before production changes"
    elif destructive_guards and not strong_guards:
        edge_verdict = "NO_EDGE_DETECTED"
        confidence = "MEDIUM"
        main_risk = "Guard behavior is associated with negative expectancy"
        recommended = "Rework or disable destructive guard logic and re-test"
    elif promising_regimes and unstable_regimes:
        edge_verdict = "REGIME_DEPENDENT_EDGE"
        confidence = "MEDIUM"
        main_risk = "Edge is uneven across regimes"
        recommended = "Restrict deployment to stronger regimes and validate routing rules"
    elif unstable_regimes and not promising_regimes:
        edge_verdict = "UNSTABLE_EDGE"
        confidence = "LOW"
        main_risk = "Performance is unstable across contexts"
        recommended = "Stabilize guard behavior and evaluate by symbol/session slices"
    elif strong_guards and avg_quality >= 1.0 and total_quality >= 100:
        edge_verdict = "PROMOTION_CANDIDATE"
        confidence = "HIGH"
        main_risk = "Residual execution variance"
        recommended = "Proceed with controlled promotion gates and continued monitoring"
    elif strong_guards:
        edge_verdict = "PROMISING_BUT_UNPROVEN"
        confidence = "MEDIUM"
        main_risk = "Protective signal exists but confidence is not yet high"
        recommended = "Collect more cycles and confirm cross-regime consistency"
    else:
        edge_verdict = "NO_EDGE_DETECTED"
        confidence = "LOW"
        main_risk = "No protective pattern identified in current data"
        recommended = "Review strategy assumptions and run targeted experiments"

    run_id = None
    for row in decision_quality:
        if row.get("run_id"):
            run_id = row["run_id"]
            break

    return {
        "run_id": run_id,
        "edge_verdict": edge_verdict,
        "confidence": confidence,
        "main_strength": (
            f"{len(strong_guards)} guard(s) show protective behavior"
            if strong_guards
            else "No clearly protective guard detected"
        ),
        "main_risk": main_risk,
        "recommended_next_action": recommended,
        "warning_count": len(warnings),
    }

