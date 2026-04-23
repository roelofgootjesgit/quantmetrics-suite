"""Generate markdown research logs from experiment + metric dicts."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from quantresearch.metrics_normalize import normalize_metrics
from quantresearch.paths import research_logs_dir, templates_dir


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _slug(s: str, max_len: int = 40) -> str:
    t = re.sub(r"[^a-zA-Z0-9_-]+", "_", s.strip().lower()).strip("_")
    return (t[:max_len] if t else "experiment").rstrip("_")


def build_research_log_markdown(
    *,
    experiment_id: str,
    date_str: str,
    baseline_run_id: str,
    variant_run_id: str,
    baseline_config: str,
    variant_config: str,
    data_window: dict[str, str] | None,
    strategy_version: str,
    hypothesis: str,
    intervention: str = "",
    expectation: str = "",
    baseline_metrics: dict[str, Any] | None,
    variant_metrics: dict[str, Any] | None,
    analysis: str = "",
    conclusion: str = "",
    decision: str = "",
    next_step: str = "",
    template_path: Path | None = None,
) -> str:
    tpl_path = template_path or (templates_dir() / "research_log_template.md")
    text = tpl_path.read_text(encoding="utf-8")

    b = normalize_metrics(baseline_metrics or {})
    v = normalize_metrics(variant_metrics or {})

    dw = ""
    if data_window:
        dw = f"{data_window.get('start', '')} → {data_window.get('end', '')}"

    repl = {
        "experiment_id": experiment_id,
        "date": date_str,
        "baseline_run_id": baseline_run_id,
        "variant_run_id": variant_run_id,
        "baseline_config": baseline_config,
        "variant_config": variant_config,
        "data_window": dw,
        "strategy_version": strategy_version,
        "hypothesis": hypothesis,
        "intervention": intervention,
        "expectation": expectation,
        "analysis": analysis,
        "conclusion": conclusion,
        "decision": decision,
        "next_step": next_step,
        "baseline_trades": _fmt(b.get("trade_count")),
        "baseline_mean_r": _fmt(b.get("mean_r")),
        "baseline_winrate": _fmt(b.get("winrate")),
        "baseline_avg_mae_r": _fmt(b.get("avg_mae_r")),
        "baseline_avg_mfe_r": _fmt(b.get("avg_mfe_r")),
        "baseline_drawdown": _fmt(b.get("drawdown")),
        "variant_trades": _fmt(v.get("trade_count")),
        "variant_mean_r": _fmt(v.get("mean_r")),
        "variant_winrate": _fmt(v.get("winrate")),
        "variant_avg_mae_r": _fmt(v.get("avg_mae_r")),
        "variant_avg_mfe_r": _fmt(v.get("avg_mfe_r")),
        "variant_drawdown": _fmt(v.get("drawdown")),
    }

    out = text
    for k, val in repl.items():
        out = out.replace("{{" + k + "}}", val)
    return out


def write_research_log(
    markdown: str,
    *,
    experiment_id: str,
    title_slug: str,
    date_str: str | None = None,
    out_dir: Path | None = None,
) -> Path:
    """Filename: YYYY-MM-DD_EXP-XXX_slug.md"""
    base = out_dir or research_logs_dir()
    base.mkdir(parents=True, exist_ok=True)
    ds = date_str or date.today().isoformat()
    safe_slug = _slug(title_slug)
    name = f"{ds}_{experiment_id}_{safe_slug}.md"
    path = base / name
    path.write_text(markdown, encoding="utf-8")
    return path


def build_and_write_log(title_slug: str, **kwargs: Any) -> Path:
    """Convenience: build markdown and write under research_logs/."""
    if not kwargs.get("date_str"):
        kwargs["date_str"] = date.today().isoformat()
    md = build_research_log_markdown(**kwargs)
    return write_research_log(
        md,
        experiment_id=str(kwargs["experiment_id"]),
        title_slug=title_slug,
        date_str=str(kwargs["date_str"]),
    )
