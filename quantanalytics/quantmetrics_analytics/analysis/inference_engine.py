"""Per-trade R inferential layer (Wilcoxon-first, bootstrap CI, Cohen's d)."""

from __future__ import annotations

import math
import statistics
import warnings
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import stats
from scipy.stats import bootstrap

TestUsed = Literal["wilcoxon_signed_rank", "one_sample_t", "none"]
EffectInterpretation = Literal["negligible", "small", "medium", "large"]
StatVerdict = Literal["PASS", "FAIL", "INSUFFICIENT_N"]
EconVerdict = Literal["PASS", "FAIL", "PENDING"]


@dataclass
class InferenceResult:
    n: int
    mean_r: float
    std_r: float
    median_r: float
    shapiro_wilk_p: float | None
    test_used: TestUsed
    p_value: float | None
    significant_at_alpha: bool | None
    alpha_used: float
    ci_95_lower: float
    ci_95_upper: float
    bootstrap_iterations: int
    bootstrap_seed: int
    cohens_d: float
    effect_interpretation: EffectInterpretation
    statistical_verdict: StatVerdict
    economic_verdict: EconVerdict
    minimum_effect_size_used: float
    ci_method: str


def _interpret_cohen_d(d: float) -> EffectInterpretation:
    a = abs(float(d))
    if a < 0.2:
        return "negligible"
    if a < 0.5:
        return "small"
    if a < 0.8:
        return "medium"
    return "large"


def _shapiro_p(x: np.ndarray) -> float | None:
    n = int(x.size)
    if n < 3 or n > 5000:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        try:
            _, p = stats.shapiro(x)
        except ValueError:
            return None
    return float(p)


def _cohens_d(x: np.ndarray) -> float:
    if x.size < 2:
        return 0.0
    m = float(np.mean(x))
    s = float(np.std(x, ddof=1))
    if s <= 0.0 or math.isnan(s):
        return 0.0
    return m / s


def _bootstrap_ci_mean(
    x: np.ndarray, n_resamples: int, seed: int
) -> tuple[float, float, str]:
    """95% CI on mean; BCa when scipy accepts, else percentile bootstrap on the mean."""
    rng = np.random.default_rng(seed)
    if x.size == 0:
        return float("nan"), float("nan"), "none"
    if x.size == 1:
        v = float(x[0])
        return v, v, "single_observation"
    try:
        res = bootstrap(
            (x,),
            np.mean,
            confidence_level=0.95,
            n_resamples=min(n_resamples, 50_000),
            random_state=rng,
            method="BCa",
        )
        lo, hi = float(res.confidence_interval.low), float(res.confidence_interval.high)
        if math.isfinite(lo) and math.isfinite(hi):
            return lo, hi, "bootstrap_bca"
    except (ValueError, RuntimeError):
        pass
    # Percentile bootstrap fallback
    means = np.empty(min(n_resamples, 50_000), dtype=float)
    for i in range(means.size):
        sample = rng.choice(x, size=x.size, replace=True)
        means[i] = float(np.mean(sample))
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), "bootstrap_percentile"


def run_inference(
    r_series: list[float],
    *,
    alpha: float = 0.05,
    minimum_n: int = 300,
    minimum_effect_size_r: float = 0.028,
    bootstrap_iterations: int = 10_000,
    bootstrap_seed: int = 42,
    h0_median: float = 0.0,
) -> InferenceResult:
    x_list = [float(v) for v in r_series if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n = len(x_list)
    mean_r = float(statistics.mean(x_list)) if n else 0.0
    std_r = float(statistics.stdev(x_list)) if n > 1 else 0.0
    median_r = float(statistics.median(x_list)) if n else 0.0
    minimum_effect_size_used = float(minimum_effect_size_r)

    if n < minimum_n:
        return InferenceResult(
            n=n,
            mean_r=mean_r,
            std_r=std_r,
            median_r=median_r,
            shapiro_wilk_p=None,
            test_used="none",
            p_value=None,
            significant_at_alpha=None,
            alpha_used=float(alpha),
            ci_95_lower=float("nan"),
            ci_95_upper=float("nan"),
            bootstrap_iterations=int(bootstrap_iterations),
            bootstrap_seed=int(bootstrap_seed),
            cohens_d=_cohens_d(np.asarray(x_list, dtype=float)),
            effect_interpretation=_interpret_cohen_d(_cohens_d(np.asarray(x_list, dtype=float))),
            statistical_verdict="INSUFFICIENT_N",
            economic_verdict="PENDING",
            minimum_effect_size_used=minimum_effect_size_used,
            ci_method="none",
        )

    arr = np.asarray(x_list, dtype=float)
    shapiro_p = _shapiro_p(arr)
    is_normal = shapiro_p is not None and shapiro_p > 0.05

    centered = arr - float(h0_median)
    p_value: float | None
    test_used: TestUsed
    if is_normal:
        test_used = "one_sample_t"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UserWarning)
            res = stats.ttest_1samp(centered, popmean=0.0, alternative="two-sided")
        p_value = float(res.pvalue)
    else:
        test_used = "wilcoxon_signed_rank"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=UserWarning)
                res = stats.wilcoxon(centered, zero_method="wilcox", alternative="two-sided", mode="auto")
            p_value = float(res.pvalue)
        except ValueError:
            p_value = 1.0

    ci_lo, ci_hi, ci_method = _bootstrap_ci_mean(arr, bootstrap_iterations, bootstrap_seed)
    d = _cohens_d(arr)
    effect = _interpret_cohen_d(d)

    assert p_value is not None
    significant = p_value < alpha
    stat_verdict: StatVerdict = "PASS" if significant else "FAIL"
    # Economic gate: entire 95% CI must clear the floor (not the point mean).
    econ_verdict: EconVerdict = (
        "PASS" if (math.isfinite(ci_lo) and ci_lo >= minimum_effect_size_r) else "FAIL"
    )

    return InferenceResult(
        n=n,
        mean_r=mean_r,
        std_r=std_r,
        median_r=median_r,
        shapiro_wilk_p=shapiro_p,
        test_used=test_used,
        p_value=p_value,
        significant_at_alpha=significant,
        alpha_used=float(alpha),
        ci_95_lower=ci_lo,
        ci_95_upper=ci_hi,
        bootstrap_iterations=int(bootstrap_iterations),
        bootstrap_seed=int(bootstrap_seed),
        cohens_d=float(d),
        effect_interpretation=effect,
        statistical_verdict=stat_verdict,
        economic_verdict=econ_verdict,
        minimum_effect_size_used=minimum_effect_size_used,
        ci_method=ci_method,
    )
