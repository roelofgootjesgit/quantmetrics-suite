"""Write ``guard_attribution_<run_id>.json`` and ``.md``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_markdown(payload: dict[str, Any]) -> str:
    meta = payload.get("meta", {})
    run_id = meta.get("run_id", "")
    summary = payload.get("guard_summary", {})
    gt = payload.get("guard_score_table", [])
    ctx = payload.get("context_summary", {})

    lines: list[str] = [
        "# Guard Attribution Report",
        "",
        "## Summary",
        "",
        f"- **run_id**: `{run_id}`",
        f"- **total_blocks**: {meta.get('total_blocks', 0)}",
        f"- **Most dominant guard**: `{summary.get('most_dominant_guard')}` ({summary.get('dominant_share', 0):.2%} of blocks)",
        f"- **Largest throughput cost (block count)**: `{summary.get('largest_throughput_guard')}`",
        f"- **Likely overblocking** (heuristic): {', '.join(summary.get('likely_overblocking_guards') or []) or '—'}",
        "",
        "### Context (all blocking guards combined)",
        "",
        f"- By regime: `{ctx.get('by_regime', {})}`",
        f"- By session: `{ctx.get('by_session', {})}`",
        "",
        "> Slice counterfactuals are **approximate** (same-regime/session/setup executed mean). "
        "See JSON for per-row sample sizes and fallback flags.",
        "",
        "## Guard score table",
        "",
        "| Guard | Blocks | Share | Missed W (cnt) | Avoided L (cnt) | Net block value (R) | Mean est. R | Assessment |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]

    for r in gt:
        lines.append(
            "| {guard} | {blocks} | {share:.2%} | {mw} | {al} | {net} | {meaner} | {asm} |".format(
                guard=r.get("guard_name", ""),
                blocks=r.get("blocks", 0),
                share=float(r.get("share_of_all_blocks") or 0),
                mw=r.get("estimated_missed_winners_count", 0),
                al=r.get("estimated_avoided_losers_count", 0),
                net=r.get("net_block_value_r", 0),
                meaner=r.get("mean_estimated_r", 0),
                asm=r.get("assessment", ""),
            )
        )

    lines.extend(
        [
            "",
            "## Research notes",
            "",
            "- Prefer **guard-off reruns** before changing production filters.",
            "- Treat `likely_*` labels as hypotheses, not directives.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def write_reports(output_dir: Path, run_id: str, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in run_id)
    js = output_dir / f"guard_attribution_{safe}.json"
    md = output_dir / f"guard_attribution_{safe}.md"
    js.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md.write_text(render_markdown(payload), encoding="utf-8")
    return js, md
