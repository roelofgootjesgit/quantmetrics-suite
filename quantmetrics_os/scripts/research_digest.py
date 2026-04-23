#!/usr/bin/env python3
"""Scan quantmetrics_os/runs/ and write research summaries (Markdown + JSON).

Reads each ``run_info.json`` under ``runs/<experiment>/<role>/`` and pulls bundled
analytics (KEY_FINDINGS, optionally report .txt) into one digest for QuantResearch.

Usage::

    cd quantmetrics_os
    python scripts/research_digest.py

    python scripts/research_digest.py --runs-dir runs --output-dir research

"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _quantmetrics_os_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_run_bundle(role_dir: Path) -> dict[str, Any] | None:
    ri = role_dir / "run_info.json"
    if not ri.is_file():
        return None
    try:
        return json.loads(ri.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _latest_key_findings(analytics_dir: Path) -> tuple[str | None, str | None]:
    """Return (relative_filename, content) for newest *KEY_FINDINGS*.md."""
    if not analytics_dir.is_dir():
        return None, None
    candidates = sorted(
        analytics_dir.glob("*KEY_FINDINGS*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None, None
    p = candidates[0]
    try:
        return p.name, p.read_text(encoding="utf-8")
    except OSError:
        return p.name, None


def _latest_report_snippet(analytics_dir: Path, max_lines: int = 120) -> tuple[str | None, str | None]:
    """Newest quantlog_events_*.txt first N lines."""
    if not analytics_dir.is_dir():
        return None, None
    txts = sorted(
        [p for p in analytics_dir.glob("quantlog_events_*.txt") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not txts:
        return None, None
    p = txts[0]
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        body = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            body += f"\n\n… ({len(lines) - max_lines} more lines)"
        return p.name, body
    except OSError:
        return p.name, None


def scan_runs(runs_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not runs_root.is_dir():
        return rows

    for exp_dir in sorted(runs_root.iterdir()):
        if not exp_dir.is_dir() or exp_dir.name.startswith("."):
            continue
        for role_dir in sorted(exp_dir.iterdir()):
            if not role_dir.is_dir() or role_dir.name.startswith("."):
                continue
            bundle = _load_run_bundle(role_dir)
            if bundle is None:
                continue
            rel = f"{exp_dir.name}/{role_dir.name}"
            analytics_dir = role_dir / "analytics"
            kf_name, kf_body = _latest_key_findings(analytics_dir)
            txt_name, txt_snip = _latest_report_snippet(analytics_dir)

            ql = role_dir / "quantlog_events.jsonl"
            cfg = role_dir / "config_snapshot.yaml"

            rows.append(
                {
                    "experiment_folder": exp_dir.name,
                    "role": role_dir.name,
                    "path": str(role_dir.resolve()),
                    "relative_path": rel,
                    "bundle": bundle,
                    "quantlog_events_bytes": ql.stat().st_size if ql.is_file() else 0,
                    "has_config_snapshot": cfg.is_file(),
                    "key_findings_file": kf_name,
                    "key_findings_chars": len(kf_body) if kf_body else 0,
                    "report_txt_file": txt_name,
                    "key_findings_excerpt": kf_body,
                    "report_txt_excerpt": txt_snip,
                }
            )
    return rows


def render_markdown(rows: list[dict[str, Any]], generated_utc: str) -> str:
    lines = [
        "# Runs research digest",
        "",
        f"*Generated (UTC): {generated_utc}*",
        "",
        "Automatisch samengesteld uit `runs/` — één plek om gebundelde backtests en analytics te overzien.",
        "",
        "## Overzicht",
        "",
        "| Experiment | Role | run_id | Verzameld (UTC) | JSONL (KB) | KEY_FINDINGS |",
        "|------------|------|--------|-----------------|------------|--------------|",
    ]

    for r in rows:
        b = r["bundle"]
        rid = str(b.get("run_id", ""))
        coll = str(b.get("collected_at_utc", ""))[:19]
        kb = round(r.get("quantlog_events_bytes", 0) / 1024, 1)
        kf = "ja" if r.get("key_findings_chars") else "—"
        lines.append(
            f"| {r['experiment_folder']} | {r['role']} | `{rid}` | {coll} | {kb} | {kf} |"
        )

    lines.extend(["", "---", ""])

    for r in rows:
        b = r["bundle"]
        lines.append(f"## {r['experiment_folder']} / {r['role']}")
        lines.append("")
        lines.append(f"- **run_id:** `{b.get('run_id')}`")
        lines.append(f"- **experiment_id (manifest):** `{b.get('experiment_id')}`")
        lines.append(f"- **Verzameld:** {b.get('collected_at_utc')}")
        lines.append(f"- **QuantLog bron:** `{b.get('quantlog_source')}`")
        lines.append(f"- **Config snapshot:** `{b.get('config_snapshot')}` (`{b.get('config_source_path')}`)")
        lines.append("")

        kf = r.get("key_findings_excerpt")
        if kf:
            lines.append("### Bevindingen (KEY_FINDINGS)")
            lines.append("")
            lines.append("```markdown")
            # cap extremely long paste
            max_c = 16000
            lines.append(kf[:max_c] + ("…\n(truncated)" if len(kf) > max_c else ""))
            lines.append("```")
            lines.append("")
        else:
            lines.append("*Geen KEY_FINDINGS in `analytics/` — bundle opnieuw met `bundle_analytics: true` of kopieer handmatig.*")
            lines.append("")

        txt = r.get("report_txt_excerpt")
        if txt and not kf:
            lines.append("### Analytics rapport (fragment)")
            lines.append("")
            lines.append("```text")
            lines.append(txt[:12000])
            lines.append("```")
            lines.append("")

        lines.append("---")
        lines.append("")

    if not rows:
        lines.extend(["*Geen bundles gevonden onder `runs/` — nog geen artifact-collect gedraaid.*", ""])

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate research digest from quantmetrics_os/runs/")
    parser.add_argument("--runs-dir", type=Path, default=None, help="Default: <repo>/runs")
    parser.add_argument("--output-dir", type=Path, default=None, help="Default: <repo>/research")
    args = parser.parse_args()

    root = _quantmetrics_os_root()
    runs_root = (args.runs_dir or (root / "runs")).resolve()
    out_dir = (args.output_dir or (root / "research")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = scan_runs(runs_root)
    gen = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    md_path = out_dir / "runs_digest.md"
    js_path = out_dir / "runs_registry.json"

    md_path.write_text(render_markdown(rows, gen), encoding="utf-8")

    registry = {
        "generated_at_utc": gen,
        "runs_root": str(runs_root),
        "bundles": [],
    }
    for r in rows:
        entry = {
            "experiment_folder": r["experiment_folder"],
            "role": r["role"],
            "path": r["path"],
            "run_info": r["bundle"],
            "quantlog_events_bytes": r["quantlog_events_bytes"],
            "has_config_snapshot": r["has_config_snapshot"],
            "key_findings_file": r["key_findings_file"],
            "report_txt_file": r["report_txt_file"],
        }
        registry["bundles"].append(entry)

    js_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {md_path}")
    print(f"Wrote {js_path}")
    print(f"Bundles: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
