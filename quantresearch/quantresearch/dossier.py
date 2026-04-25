"""Assemble EXPERIMENT_DOSSIER.md from existing QuantResearch / QuantOS / QuantAnalytics artifacts only."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantresearch.ledger import experiment_path, load_experiment, load_links


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path, *, max_chars: int) -> str | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    if len(raw) > max_chars:
        return raw[:max_chars] + "\n\n… *(truncated for dossier size cap)*\n"
    return raw


def _suite_root(exp: dict[str, Any]) -> Path | None:
    suite = exp.get("suite") if isinstance(exp.get("suite"), dict) else {}
    root = suite.get("suite_root")
    if not root or not str(root).strip():
        return None
    return Path(str(root)).resolve()


def _resolve_under_suite(suite_root: Path, rel: str, *, absolute_ok: bool) -> Path:
    p = Path(rel)
    if absolute_ok and p.is_absolute():
        return p.resolve()
    return (suite_root / rel).resolve()


def _md_escape_cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


@dataclass
class _ArtifactBundle:
    suite_root: Path | None = None
    run_dir: Path | None = None
    compare_json: Path | None = None
    compare_md: Path | None = None
    registry_json: Path | None = None
    summary_md: Path | None = None
    compare_data: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


def _load_quantos_bundle(exp: dict[str, Any], links: dict[str, Any] | None) -> _ArtifactBundle:
    b = _ArtifactBundle()
    if not links:
        b.warnings.append("No `links.json`: QuantOS run is not linked; dossier cannot list matrix artifacts.")
        return b

    b.suite_root = _suite_root(exp)
    if not b.suite_root or not b.suite_root.is_dir():
        b.warnings.append("Missing or invalid `suite.suite_root` in experiment.json — cannot resolve QuantOS paths.")
        return b

    abs_ok = bool(links.get("paths_are_absolute"))
    qrd = str(links.get("quantos_run_dir", "") or "").strip()
    if not qrd:
        b.warnings.append("links.json missing `quantos_run_dir`.")
        return b

    b.run_dir = _resolve_under_suite(b.suite_root, qrd, absolute_ok=abs_ok)
    if not b.run_dir.is_dir():
        b.warnings.append(f"QuantOS run directory does not exist: {b.run_dir}")

    for key, attr in (
        ("throughput_compare_json", "compare_json"),
        ("throughput_compare_md", "compare_md"),
        ("throughput_discovery_registry", "registry_json"),
        ("throughput_discovery_summary", "summary_md"),
    ):
        rel = str(links.get(key, "") or "").strip()
        if not rel:
            b.warnings.append(f"links.json missing `{key}`.")
            continue
        p = _resolve_under_suite(b.suite_root, rel, absolute_ok=abs_ok)
        setattr(b, attr, p)
        if not p.is_file():
            b.warnings.append(f"Linked artifact not found: {p}")

    if b.compare_json and b.compare_json.is_file():
        try:
            b.compare_data = _read_json(b.compare_json)
        except (OSError, json.JSONDecodeError) as e:
            b.warnings.append(f"Cannot read THROUGHPUT_COMPARE.json: {e}")
    elif b.compare_json:
        b.warnings.append(f"THROUGHPUT_COMPARE.json missing: {b.compare_json}")

    return b


def _edge_verdict_rows(run_dir: Path | None, variants: list[dict[str, Any]], warnings: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not run_dir or not run_dir.is_dir():
        return rows
    for v in variants:
        folder = str(v.get("variant_folder") or v.get("variant") or "").strip()
        if not folder:
            continue
        p = run_dir / folder / "analytics" / "edge_verdict.json"
        if not p.is_file():
            warnings.append(f"Missing edge verdict: `{p}`")
            rows.append(
                {
                    "variant_folder": folder,
                    "edge_verdict": "—",
                    "confidence": "—",
                    "main_risk": "—",
                }
            )
            continue
        try:
            data = _read_json(p)
        except (OSError, json.JSONDecodeError) as e:
            warnings.append(f"Cannot read `{p}`: {e}")
            continue
        rows.append(
            {
                "variant_folder": folder,
                "edge_verdict": str(data.get("edge_verdict", "—")),
                "confidence": str(data.get("confidence", "—")),
                "main_risk": str(data.get("main_risk", "—"))[:200],
            }
        )
    return rows


def render_experiment_dossier_md(experiment_id: str) -> tuple[str, list[str]]:
    """Return (markdown, warnings). Does not write files."""
    warnings: list[str] = []
    exp_dir = experiment_path(experiment_id)
    try:
        exp = load_experiment(experiment_id)
    except FileNotFoundError as e:
        raise FileNotFoundError(str(e)) from e

    links = load_links(experiment_id)
    bundle = _load_quantos_bundle(exp, links)

    gen = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines: list[str] = [
        f"# Experiment dossier: `{experiment_id}`",
        "",
        f"Generated at (UTC): `{gen}`",
        "",
        "This file is assembled **only** from existing QuantResearch, QuantOS, and QuantAnalytics outputs. "
        "QuantResearch does **not** recompute trading metrics here.",
        "",
        "## Auditor notice: discovery tiers are not promotion",
        "",
        "- **WATCHLIST** is a throughput-compare triage label for follow-up experiment design. It is **not** production promotion.",
        "- **RELAX_CANDIDATE** is a stricter triage label (per compare rules). It is **still not** promotion by itself.",
        "- **PROMOTION** to production (or live deployment) requires an explicit **QuantOS promotion gate** outcome consistent with ledger rules; "
        "compare tables, clusters, and edge verdicts are evidence inputs, not promotion by themselves.",
        "",
    ]

    lines.extend(["## 1. Experiment metadata", ""])
    meta_rows = [
        ("experiment_id", exp.get("experiment_id")),
        ("title", exp.get("title")),
        ("status", exp.get("status")),
        ("created_at_utc", exp.get("created_at_utc")),
        ("completed_at_utc", exp.get("completed_at_utc")),
        ("matrix_type", exp.get("matrix_type")),
        ("hypothesis_summary", exp.get("hypothesis_summary")),
        ("primary_metric", exp.get("primary_metric")),
        ("promotion_decision (ledger)", exp.get("promotion_decision")),
        ("discovery_tier (ledger)", exp.get("discovery_tier")),
        ("baseline_run_id", exp.get("baseline_run_id")),
        ("canonical_artifact_path", exp.get("canonical_artifact_path")),
    ]
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    for k, v in meta_rows:
        val = "" if v is None else str(v)
        lines.append(f"| {k} | {_md_escape_cell(val)} |")
    lines.append("")

    lines.extend(["## 2. Parent / rerun lineage", ""])
    parent = str(exp.get("parent_experiment_id", "") or "").strip()
    if parent:
        lines.extend(
            [
                f"- **parent_experiment_id:** `{parent}`",
                f"- **rerun_reason:** {exp.get('rerun_reason', '')}",
                f"- **rerun_index:** {exp.get('rerun_index', '')}",
                f"- **previous_completed_at_utc:** `{exp.get('previous_completed_at_utc', '')}`",
                "",
            ]
        )
    else:
        lines.append("*No rerun lineage fields on this experiment (treat as primary ledger entry unless manually edited).*")
        lines.append("")

    def _embed_md(title: str, rel_name: str) -> None:
        path = exp_dir / rel_name
        if not path.is_file():
            warnings.append(f"Missing `{rel_name}` under experiment folder.")
            lines.extend([f"## {title}", "", f"*Missing file: `{path}`*", ""])
            return
        body = _read_text(path, max_chars=100_000)
        lines.extend([f"## {title}", "", body or "", ""])

    _embed_md("3. Hypothesis", "hypothesis.md")
    _embed_md("4. Experiment plan", "experiment_plan.md")

    lines.extend(["## 5. Linked QuantOS artifacts", ""])
    if links:
        lines.append("From `links.json` (paths resolved via `suite.suite_root` when relative):")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(links, indent=2))
        lines.append("```")
        lines.append("")
        if bundle.run_dir:
            lines.append(f"- **QuantOS run root:** `{bundle.run_dir}`")
        for label, pth in (
            ("THROUGHPUT_COMPARE.json", bundle.compare_json),
            ("THROUGHPUT_COMPARE.md", bundle.compare_md),
            ("throughput_discovery_registry.json", bundle.registry_json),
            ("THROUGHPUT_DISCOVERY_SUMMARY.md", bundle.summary_md),
        ):
            if pth:
                ok = "✓" if pth.is_file() else "✗"
                lines.append(f"- {ok} **{label}:** `{pth}`")
        if bundle.registry_json and bundle.registry_json.is_file():
            try:
                reg = _read_json(bundle.registry_json)
                n = len(reg.get("rows", [])) if isinstance(reg.get("rows"), list) else 0
                lines.append(f"- **Registry variant rows:** {n}")
            except (OSError, json.JSONDecodeError):
                pass
        lines.append("")
        if bundle.run_dir and bundle.run_dir.is_dir():
            lines.append("**Role folders (first-level under run root):**")
            lines.append("")
            subs = sorted(d.name for d in bundle.run_dir.iterdir() if d.is_dir() and not d.name.startswith("."))
            for name in subs[:40]:
                lines.append(f"- `{name}/`")
            if len(subs) > 40:
                lines.append(f"- … *({len(subs) - 40} more)*")
            lines.append("")
    else:
        lines.append("*No `links.json` yet — link a QuantOS run after orchestration (`quantresearch link-artifacts`).*")
        lines.append("")

    variants: list[dict[str, Any]] = []
    if bundle.compare_data and isinstance(bundle.compare_data.get("variants"), list):
        variants = bundle.compare_data["variants"]

    lines.extend(["## 6. Throughput compare (QuantAnalytics / QuantOS compare output)", ""])
    if bundle.compare_data:
        lines.append(f"- **Compare generated_at_utc:** `{bundle.compare_data.get('generated_at_utc', '')}`")
        lines.append(f"- **Baseline folder:** `{bundle.compare_data.get('baseline_variant_folder', '')}`")
        conc6 = bundle.compare_data.get("conclusions")
        conc6 = conc6 if isinstance(conc6, dict) else None
        if conc6:
            for key in ("best_throughput_variant", "best_quality_variant", "best_balanced_variant"):
                if conc6.get(key):
                    lines.append(f"- **{key}:** `{conc6.get(key)}`")
        lines.append("")
        lines.append("| Variant | promotion (compare) | confidence | trades | exp R | PF | max DD R |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for v in variants:
            lines.append(
                "| "
                + " | ".join(
                    _md_escape_cell(str(x))
                    for x in (
                        v.get("variant_folder", v.get("variant")),
                        v.get("promotion_decision"),
                        v.get("confidence"),
                        v.get("total_trades"),
                        round(float(v["expectancy_r"]), 4) if v.get("expectancy_r") is not None else "",
                        round(float(v["profit_factor"]), 4) if v.get("profit_factor") is not None else "",
                        round(float(v["max_drawdown_r"]), 4) if v.get("max_drawdown_r") is not None else "",
                    )
                )
                + " |"
            )
        lines.append("")
        notes = conc6.get("notes") if conc6 else None
        if isinstance(notes, list) and notes:
            lines.append("**Compare notes (verbatim):**")
            lines.append("")
            for n in notes:
                lines.append(f"- {_md_escape_cell(str(n))}")
            lines.append("")
    else:
        lines.append("*No THROUGHPUT_COMPARE.json loaded — section skipped.*")
        lines.append("")

    lines.extend(["## 7. Discovery tiers & clusters", ""])
    conc = bundle.compare_data.get("conclusions") if bundle.compare_data else None
    if isinstance(conc, dict):
        drs = conc.get("discovery_rule_summary")
        if drs is not None:
            lines.append("### discovery_rule_summary")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(drs, indent=2))
            lines.append("```")
            lines.append("")
        wv = conc.get("watchlist_by_variant")
        if isinstance(wv, dict) and wv:
            lines.append("### watchlist_by_variant")
            lines.append("")
            for vk, vv in sorted(wv.items()):
                lines.append(f"- **`{vk}`:** {_md_escape_cell(str(vv))}")
            lines.append("")
        rv = conc.get("relax_candidate_by_variant")
        if isinstance(rv, dict) and rv:
            lines.append("### relax_candidate_by_variant")
            lines.append("")
            for vk, vv in sorted(rv.items()):
                lines.append(f"- **`{vk}`:** {_md_escape_cell(str(vv))}")
            lines.append("")
        clusters = conc.get("discovery_clusters")
        if isinstance(clusters, list) and clusters:
            lines.append("### discovery_clusters")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(clusters, indent=2))
            lines.append("```")
            lines.append("")
        for bucket in ("guards_to_watchlist", "guards_to_relax_candidate", "guards_to_investigate"):
            items = conc.get(bucket)
            if isinstance(items, list) and items:
                lines.append(f"### {bucket}")
                lines.append("")
                for it in items:
                    lines.append(f"- {_md_escape_cell(str(it))}")
                lines.append("")
    else:
        lines.append("*No conclusions block in compare JSON.*")
        lines.append("")

    lines.extend(["## 8. Promotion decisions (per variant, from compare JSON)", ""])
    if variants:
        lines.append("Values below are **QuantOS compare / gate labels** as recorded in THROUGHPUT_COMPARE.json, not an independent QuantResearch computation.")
        lines.append("")
    else:
        lines.append("*No variant rows available.*")
        lines.append("")

    lines.extend(["## 9. Edge verdicts (QuantAnalytics per variant)", ""])
    ev_rows = _edge_verdict_rows(bundle.run_dir, variants, warnings)
    if ev_rows:
        lines.append("| Variant folder | edge_verdict | confidence | main_risk (trunc.) |")
        lines.append("| --- | --- | --- | --- |")
        for r in ev_rows:
            lines.append(
                "| "
                + " | ".join(_md_escape_cell(str(r[k])) for k in ("variant_folder", "edge_verdict", "confidence", "main_risk"))
                + " |"
            )
        lines.append("")
    else:
        lines.append("*No edge verdict rows (missing run dir or compare variants).*")
        lines.append("")

    lines.extend(["## 10. Final decision (QuantResearch)", ""])
    dec_path = exp_dir / "decision.md"
    if dec_path.is_file():
        body = _read_text(dec_path, max_chars=80_000)
        lines.append(body or "")
        lines.append("")
    else:
        warnings.append("Missing decision.md")
        lines.append(f"*Missing `{dec_path}`*")
        lines.append("")

    lines.extend(["## 11. Next action", ""])
    lines.append(f"- **next_action (ledger):** `{exp.get('next_action', '')}`")
    ne = exp.get("next_experiment_id")
    lines.append(f"- **next_experiment_id:** `{ne if ne else ''}`")
    rs = exp_dir / "results_summary.md"
    if rs.is_file():
        lines.append("")
        lines.append("### results_summary.md (excerpt)")
        lines.append("")
        excerpt = _read_text(rs, max_chars=8_000)
        lines.append(excerpt or "")
    lines.append("")

    all_warnings = list(bundle.warnings) + warnings
    if all_warnings:
        try:
            insert_at = lines.index("## 1. Experiment metadata")
        except ValueError:
            insert_at = 0
        block = ["## Warnings", ""] + [f"- ⚠ {w}" for w in all_warnings] + [""]
        for i, line in enumerate(block):
            lines.insert(insert_at + i, line)

    return "\n".join(lines), all_warnings


def write_experiment_dossier(experiment_id: str) -> Path:
    """Write `EXPERIMENT_DOSSIER.md` under the experiment folder."""
    md, _warnings = render_experiment_dossier_md(experiment_id)
    out = experiment_path(experiment_id) / "EXPERIMENT_DOSSIER.md"
    out.write_text(md, encoding="utf-8")
    return out
