"""Render markdown research index from registries (does not overwrite README.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantresearch.edge_registry import load_confirmed, load_rejected
from quantresearch.experiment_registry import list_experiments
from quantresearch.paths import repo_root


def render_research_index(
    *,
    open_questions: list[str] | None = None,
    next_experiments: list[str] | None = None,
) -> str:
    """Build markdown: experiments table + edges + rejected + optional lists."""
    experiments = list_experiments()
    confirmed = load_confirmed()
    rejected = load_rejected()

    lines: list[str] = [
        "# Research index",
        "",
        "_Auto-generated from `registry/`. Regenerate with `write_research_index()` after updating JSON registries._",
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
        lines.append("- _(none — pass `open_questions=` to `write_research_index()` or edit after generate)_")

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


def write_research_index(
    path: Path | None = None,
    *,
    open_questions: list[str] | None = None,
    next_experiments: list[str] | None = None,
) -> Path:
    """Write docs/RESEARCH_INDEX.md (default). Does not overwrite README.md."""
    out = path or (repo_root() / "docs" / "RESEARCH_INDEX.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_research_index(
            open_questions=open_questions,
            next_experiments=next_experiments,
        ),
        encoding="utf-8",
    )
    return out
