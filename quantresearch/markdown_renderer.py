"""Render human-facing markdown index (README) from registries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantresearch.edge_registry import load_confirmed, load_rejected
from quantresearch.experiment_registry import list_experiments
from quantresearch.paths import repo_root


def render_research_readme(
    *,
    open_questions: list[str] | None = None,
    next_experiments: list[str] | None = None,
) -> str:
    """Build README.md body: experiments table + edges + rejected + optional lists."""
    experiments = list_experiments()
    confirmed = load_confirmed()
    rejected = load_rejected()

    lines: list[str] = [
        "# QuantResearch",
        "",
        "QuantResearch is the hypothesis and decision layer on top of QuantAnalytics outputs.",
        "",
        "**Stack:** QuantBuild → QuantBridge → QuantLog → QuantAnalytics → **QuantResearch**.",
        "",
        "**Loop:** Hypothesis → Variant → Backtest/run → Analytics → Compare to baseline → Conclusion → Decision → Knowledge base.",
        "",
        "**Handleiding (backtest → strategy):** zie `docs/WORKFLOW_BACKTEST_NAAR_STRATEGIE.md`.",
        "",
        "## Usage (Python)",
        "",
        "```python",
        "from pathlib import Path",
        "from quantresearch.comparison_engine import compare_runs, write_comparison_artifacts, load_json_metrics",
        "from quantresearch.experiment_registry import upsert_experiment",
        "from quantresearch.markdown_renderer import write_readme",
        "",
        "cmp = compare_runs(load_json_metrics(Path('baseline.json')), load_json_metrics(Path('variant.json')), experiment_id='EXP-001')",
        "write_comparison_artifacts(cmp)",
        "write_readme()",
        "```",
        "",
        "Environment: set `QUANTRESEARCH_ROOT` if the package is imported from outside the repo root.",
        "",
        "## Experiments",
        "",
        "| ID | Date | Title | Result | Status |",
        "|----|------|-------|--------|--------|",
    ]

    for exp in sorted(experiments, key=lambda e: e.get("experiment_id", "")):
        eid = exp.get("experiment_id", "")
        ds = exp.get("date_created", "")
        title = str(exp.get("title", "")).replace("|", "\\|")
        result = exp.get("result", "")
        status = exp.get("status", "")
        lines.append(f"| {eid} | {ds} | {title} | {result} | {status} |")

    lines.extend(["", "## Confirmed edges", ""])

    for edge in confirmed.get("edges", []):
        stmt = edge.get("statement") or edge.get("id", "")
        lines.append(f"- {stmt}")

    lines.extend(["", "## Rejected hypotheses", ""])

    for item in rejected.get("rejected", []):
        stmt = item.get("statement") or item.get("id", "")
        lines.append(f"- {stmt}")

    oq = open_questions or []
    lines.extend(["", "## Open questions", ""])
    if oq:
        for q in oq:
            lines.append(f"- {q}")
    else:
        lines.append("- _(none tracked in generator — edit README or pass open_questions)_")

    ne = next_experiments or []
    lines.extend(["", "## Next experiments", ""])
    if ne:
        for n in ne:
            lines.append(f"- {n}")
    else:
        lines.append("- EXP-002 Expansion × session filtering")
        lines.append("- EXP-003 Expansion-only with regime_allowed_sessions relaxed")

    lines.append("")
    return "\n".join(lines)


def write_readme(
    path: Path | None = None,
    *,
    open_questions: list[str] | None = None,
    next_experiments: list[str] | None = None,
) -> Path:
    """Write README.md at repo root."""
    out = path or (repo_root() / "README.md")
    out.write_text(
        render_research_readme(
            open_questions=open_questions,
            next_experiments=next_experiments,
        ),
        encoding="utf-8",
    )
    return out
