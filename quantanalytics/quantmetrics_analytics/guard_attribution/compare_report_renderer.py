"""JSON + Markdown for Level B rerun comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def render_compare_markdown(payload: dict[str, Any]) -> str:
    meta = payload.get("meta", {})
    base = payload.get("baseline_metrics", {})
    var = payload.get("variant_metrics", {})
    d = payload.get("delta_trade_metrics", {})

    lines = [
        "# Guard attribution — Level B (rerun compare)",
        "",
        "## Runs",
        "",
        f"- **Baseline** (`{meta.get('baseline_run_id')}`): {meta.get('baseline_label')}",
        f"- **Variant** (`{meta.get('variant_run_id')}`): {meta.get('variant_label')}",
        "",
        "## Trade outcomes (realized)",
        "",
        "| Metric | Baseline | Variant | Delta (var − base) |",
        "|---|---:|---:|---:|",
        f"| Trades | {base.get('trade_count')} | {var.get('trade_count')} | {d.get('delta_trade_count')} |",
        f"| Mean R | {base.get('mean_r')} | {var.get('mean_r')} | {d.get('delta_mean_r')} |",
        f"| Sum R | {base.get('sum_r')} | {var.get('sum_r')} | {d.get('delta_sum_r')} |",
        f"| Win rate % | {base.get('winrate_pct')} | {var.get('winrate_pct')} | {d.get('delta_winrate_pct')} |",
        f"| Max DD (R) | {base.get('max_dd_r')} | {var.get('max_dd_r')} | {d.get('delta_max_dd_r')} |",
        f"| PF ~ | {base.get('profit_factor_like')} | {var.get('profit_factor_like')} | {d.get('delta_profit_factor_like')} |",
        "",
        "## Guard blocks (BLOCK counts)",
        "",
        "| Guard | Baseline | Variant | Δ blocks |",
        "|---|---:|---:|---:|",
    ]

    for row in payload.get("guard_blocks_table", []):
        lines.append(
            "| {g} | {b} | {v} | {db} |".format(
                g=row.get("guard_name", ""),
                b=row.get("blocks_baseline", 0),
                v=row.get("blocks_variant", 0),
                db=row.get("delta_blocks", 0),
            )
        )

    if payload.get("guard_focus_summary"):
        gf = payload["guard_focus_summary"]
        lines.extend(
            [
                "",
                "### Focus guard",
                "",
                f"- `{gf.get('guard_name')}`: blocks {gf.get('blocks_baseline')} → {gf.get('blocks_variant')} (Δ {gf.get('delta_blocks')})",
            ]
        )

    lines.extend(["", "## Notes", "", "- Deltas use **variant − baseline**.", "- Interpret together with config diff (single-guard experiments).", ""])

    return "\n".join(lines) + "\n"


def write_compare_reports(output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    meta = payload.get("meta", {})
    br = meta.get("baseline_run_id", "baseline")
    vr = meta.get("variant_run_id", "variant")
    safe_b = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(br))
    safe_v = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(vr))
    stem = f"guard_attribution_compare_{safe_b}_vs_{safe_v}"

    output_dir.mkdir(parents=True, exist_ok=True)
    js = output_dir / f"{stem}.json"
    md = output_dir / f"{stem}.md"
    js.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md.write_text(render_compare_markdown(payload), encoding="utf-8")
    return js, md
