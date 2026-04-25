#!/usr/bin/env python3
"""Build THROUGHPUT_COMPARE.json / THROUGHPUT_COMPARE.md across matrix variants."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import discovery_clusters as dcl
import discovery_tiers as dt

VARIANT_ORDER = [
    "a0_baseline",
    "a1_session_relaxed",
    "a2_regime_relaxed",
    "a3_cooldown_relaxed",
    "a4_session_regime_relaxed",
    "a5_throughput_discovery",
    "b0_baseline",
    "b1_london_only_relaxed",
    "b2_ny_only_relaxed",
    "b3_overlap_relaxed",
    "b4_full_session_relaxed",
]

# Human-readable labels for tier lines (otherwise folder name is used).
def _vf_to_matrix_style_key(vf: str) -> str:
    i = vf.find("_")
    if i > 0:
        return f"{vf[:i].upper()}_{vf[i + 1 :].upper()}"
    return vf.upper()


VARIANT_TIER_LABELS: dict[str, str] = {
    "a1_session_relaxed": "session_filter (A1)",
    "a2_regime_relaxed": "regime_filter (A2)",
    "a3_cooldown_relaxed": "cooldown (A3)",
    "a4_session_regime_relaxed": "session + regime (A4)",
    "a5_throughput_discovery": "throughput discovery (A5)",
    "b1_london_only_relaxed": "B1 expansion (London in allowed_sessions)",
    "b2_ny_only_relaxed": "B2 expansion (NY-only + hour gate relaxed)",
    "b3_overlap_relaxed": "B3 expansion (NY+Overlap, min_hour relaxed)",
    "b4_full_session_relaxed": "B4 pipeline session filter off",
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _num(x: Any) -> float | None:
    return dt.num(x)


def _protective_guard_detected(guard_attribution: dict[str, Any]) -> bool:
    for row in guard_attribution.get("guards", []):
        if str(row.get("verdict", "")).upper() == "EDGE_PROTECTIVE":
            return True
    return False


def _collect_variant_rows(experiment_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sub in sorted(experiment_root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("_") or sub.name.startswith("."):
            continue
        analytics = sub / "analytics"
        tp_path = analytics / "throughput.json"
        prom_path = analytics / "promotion_decision.json"
        ev_path = analytics / "edge_verdict.json"
        ga_path = analytics / "guard_attribution.json"
        if not tp_path.is_file() or not prom_path.is_file():
            continue
        throughput = _read_json(tp_path)
        promotion = _read_json(prom_path)
        edge_verdict = _read_json(ev_path) if ev_path.is_file() else {}
        guard_attribution = _read_json(ga_path) if ga_path.is_file() else {}
        metrics = promotion.get("metrics", {}) if isinstance(promotion.get("metrics"), dict) else {}
        risk_shape = promotion.get("risk_shape", {}) if isinstance(promotion.get("risk_shape"), dict) else {}

        rows.append(
            {
                "variant_folder": sub.name,
                "role_dir": str(sub.resolve()),
                "throughput": throughput,
                "promotion": promotion,
                "edge_verdict": edge_verdict,
                "guard_attribution": guard_attribution,
                "flat": {
                    "variant": sub.name,
                    "variant_folder": sub.name,
                    "total_trades": metrics.get("total_trades"),
                    "raw_signals_detected": throughput.get("raw_signals_detected"),
                    "signals_after_filters": throughput.get("signals_after_filters"),
                    "signals_executed": throughput.get("signals_executed"),
                    "filter_kill_ratio": throughput.get("filter_kill_ratio"),
                    "expectancy_r": metrics.get("expectancy_r"),
                    "profit_factor": metrics.get("profit_factor"),
                    "max_drawdown_r": risk_shape.get("max_drawdown_r"),
                    "protective_guard_detected": _protective_guard_detected(guard_attribution),
                    "confidence": edge_verdict.get("confidence"),
                    "promotion_decision": promotion.get("promotion_decision"),
                    "run_id": promotion.get("run_id"),
                },
            }
        )

    def sort_key(r: dict[str, Any]) -> tuple[int, str]:
        name = r["variant_folder"]
        try:
            idx = VARIANT_ORDER.index(name)
        except ValueError:
            idx = 999
        return (idx, name)

    rows.sort(key=sort_key)
    return rows


def build_compare_payload(
    *,
    experiment_id: str,
    experiment_root: Path,
    baseline_folder: str = "a0_baseline",
    max_dd_worsen_ratio: float = dt.DEFAULT_MAX_DD_WORSEN_RATIO,
) -> dict[str, Any]:
    rows = _collect_variant_rows(experiment_root)
    if not rows:
        raise RuntimeError(f"No variant analytics found under: {experiment_root}")

    baseline = next((r for r in rows if r["variant_folder"] == baseline_folder), None)
    if baseline is None:
        baseline = rows[0]

    b = baseline["flat"]
    b_trades = _num(b.get("total_trades")) or 0.0
    b_exp = _num(b.get("expectancy_r"))
    b_pf = _num(b.get("profit_factor"))
    b_dd = _num(b.get("max_drawdown_r"))
    b_conf = b.get("confidence")

    table: list[dict[str, Any]] = []
    for r in rows:
        f = r["flat"]
        trades = _num(f.get("total_trades"))
        exp = _num(f.get("expectancy_r"))
        pf = _num(f.get("profit_factor"))
        dd = _num(f.get("max_drawdown_r"))

        delta_trades = (trades - b_trades) if trades is not None else None
        delta_exp = (exp - b_exp) if (exp is not None and b_exp is not None) else None
        delta_pf = (pf - b_pf) if (pf is not None and b_pf is not None) else None
        dd_ratio = (dd / b_dd) if (dd is not None and b_dd is not None and b_dd != 0) else None

        table.append(
            {
                **f,
                "delta_trades_vs_baseline": delta_trades,
                "delta_expectancy_vs_baseline": delta_exp,
                "delta_pf_vs_baseline": delta_pf,
                "dd_worsen_ratio_vs_baseline": dd_ratio,
            }
        )

    def norm_trades(t: float | None) -> float:
        if t is None or t <= 0:
            return 0.0
        return min(t / max(b_trades, 1.0), 3.0) / 3.0

    def norm_exp(e: float | None) -> float:
        if e is None:
            return 0.0
        return max(min(e / 2.0, 1.5), -1.5) / 1.5

    def norm_pf(p: float | None) -> float:
        if p is None or p <= 0:
            return 0.0
        return min(p / 2.5, 1.2) / 1.2

    eligible_throughput = [
        r
        for r in table
        if r["variant_folder"] != baseline_folder
        and (r.get("promotion_decision") != "REJECT" or r.get("expectancy_r") is None)
    ]
    best_throughput = max(
        eligible_throughput,
        key=lambda r: (
            _num(r.get("signals_executed")) or 0.0,
            _num(r.get("total_trades")) or 0.0,
        ),
        default=None,
    )

    eligible_quality = [
        r for r in table if _num(r.get("expectancy_r")) is not None and (_num(r.get("expectancy_r")) or 0) > 0
    ]
    best_quality = max(
        eligible_quality,
        key=lambda r: (
            norm_exp(_num(r.get("expectancy_r"))),
            norm_pf(_num(r.get("profit_factor"))),
            norm_trades(_num(r.get("total_trades"))),
        ),
        default=None,
    )

    best_balanced = max(
        table,
        key=lambda r: (
            norm_trades(_num(r.get("total_trades"))),
            norm_exp(_num(r.get("expectancy_r"))),
            norm_pf(_num(r.get("profit_factor"))),
            -abs((_num(r.get("dd_worsen_ratio_vs_baseline")) or 1.0) - 1.0),
        ),
        default=None,
    )

    guards_to_keep: list[str] = []
    guards_to_relax_candidate: list[str] = []
    guards_to_watchlist: list[str] = []
    guards_to_investigate: list[str] = []
    tiered_rows: list[dict[str, Any]] = []
    relax_candidate_by_variant: dict[str, str] = {}
    watchlist_by_variant: dict[str, str] = {}

    base_tp = baseline.get("throughput", {})
    base_blocks: dict[str, int] = dict(base_tp.get("breakdowns", {}).get("guard_blocks", {}))

    def top_delta_blocks(other: dict[str, Any]) -> list[tuple[str, int]]:
        ob = dict(other.get("breakdowns", {}).get("guard_blocks", {}))
        deltas: list[tuple[str, int]] = []
        keys = set(base_blocks) | set(ob)
        for k in keys:
            deltas.append((k, int(base_blocks.get(k, 0)) - int(ob.get(k, 0))))
        deltas.sort(key=lambda x: x[1], reverse=True)
        return deltas

    a1 = next((r for r in table if r["variant_folder"] == "a1_session_relaxed"), None)
    a2 = next((r for r in table if r["variant_folder"] == "a2_regime_relaxed"), None)

    if a2 and b_exp is not None:
        e2 = _num(a2.get("expectancy_r"))
        if e2 is not None and e2 < b_exp - 1e-6:
            guards_to_keep.append("regime_session_stack (regime relaxed materially lowers expectancy vs baseline)")

    bl_tag = baseline_folder
    for r in table:
        vf = r.get("variant_folder") or r.get("variant")
        if not vf or vf == baseline_folder:
            continue
        t = _num(r.get("total_trades"))
        e = _num(r.get("expectancy_r"))
        pf = _num(r.get("profit_factor"))
        dd = _num(r.get("max_drawdown_r"))
        conf = r.get("confidence")
        tier = dt.classify_tier(
            trades=t,
            baseline_trades=b_trades,
            expectancy_r=e,
            baseline_expectancy_r=b_exp,
            profit_factor=pf,
            variant_max_dd_r=dd,
            baseline_max_dd_r=b_dd,
            variant_confidence=conf,
            baseline_confidence=b_conf,
            max_dd_worsen_ratio=max_dd_worsen_ratio,
        )
        if tier in ("relax_candidate", "watchlist"):
            tiered_rows.append(
                {
                    "variant_folder": vf,
                    "tier": tier,
                    "total_trades": t,
                    "expectancy_r": e,
                    "profit_factor": pf,
                    "max_drawdown_r": dd,
                }
            )
        label = VARIANT_TIER_LABELS.get(vf, vf)
        pct = ((float(t or 0) / b_trades) - 1.0) * 100.0 if b_trades else 0.0
        if tier == "relax_candidate":
            rline = (
                f"{label}: relax-candidate vs `{bl_tag}` (>{(dt.RELAX_TRADE_MULT - 1) * 100:.0f}% trade count, "
                f"exp≥baseline−{dt.EXP_MATERIAL_SLACK}R, PF≥{dt.PF_MIN_GATE}, "
                f"DD≤{max_dd_worsen_ratio:.2f}×baseline, confidence≥baseline; not promotion)"
            )
            relax_candidate_by_variant[vf] = rline
            guards_to_relax_candidate.append(rline)
        elif tier == "watchlist":
            wline = (
                f"{label}: discovery watchlist vs `{bl_tag}` (~{pct:.1f}% trade lift, exp>0, PF≥{dt.PF_MIN_GATE}; "
                "does not meet full relax gates — not promotion)"
            )
            watchlist_by_variant[vf] = wline
            guards_to_watchlist.append(wline)

    relax_tokens = " ".join(guards_to_relax_candidate).lower()
    watch_tokens = " ".join(guards_to_watchlist).lower()
    keep_tokens = " ".join(guards_to_keep).lower()
    for name in sorted(base_blocks.keys(), key=lambda k: int(base_blocks.get(k, 0)), reverse=True):
        if name in {"backtest_pipeline"}:
            continue
        nl = name.lower()
        if nl in relax_tokens or nl in watch_tokens or nl in keep_tokens:
            continue
        guards_to_investigate.append(name)

    rule_summary = dt.discovery_rule_summary(max_dd_worsen_ratio=max_dd_worsen_ratio)
    discovery_clusters = dcl.build_discovery_clusters(tiered_rows, variant_order=VARIANT_ORDER)

    conclusions = {
        "best_throughput_variant": best_throughput.get("variant") if best_throughput else None,
        "best_quality_variant": best_quality.get("variant") if best_quality else None,
        "best_balanced_variant": best_balanced.get("variant") if best_balanced else None,
        "guards_to_keep": sorted(set(guards_to_keep)),
        "guards_to_relax_candidate": sorted(set(guards_to_relax_candidate)),
        "guards_to_watchlist": sorted(set(guards_to_watchlist)),
        "guards_to_investigate": sorted(set(guards_to_investigate))[:25],
        "guards_to_remove_candidate": [],
        "discovery_rule_summary": rule_summary,
        "discovery_clusters": discovery_clusters,
        "relax_candidate_by_variant": relax_candidate_by_variant,
        "watchlist_by_variant": watchlist_by_variant,
        "notes": [
            "Rankings are heuristics for research triage; promotion still requires the hard gate.",
            "Do not promote on throughput alone; validate expectancy/PF/confidence and sample size.",
            "guards_to_relax_candidate and guards_to_watchlist are NOT promotion; see discovery_rule_summary.",
            "discovery_clusters is interpretive reading aid only; it does not change tier labels or promotion_decision.",
            "Avoid session curve fitting: interpret matrices as throughput vs quality trade-offs vs baseline, not best PF hunting.",
        ],
        "block_deltas_a1_vs_a0": (
            top_delta_blocks(next(x["throughput"] for x in rows if x["variant_folder"] == "a1_session_relaxed"))[:8]
            if a1
            else []
        ),
    }

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "experiment_id": experiment_id,
        "experiment_root": str(experiment_root.resolve()),
        "baseline_variant_folder": baseline_folder,
        "variants": table,
        "conclusions": conclusions,
    }


def _render_discovery_rule_summary_md(summary: dict[str, Any]) -> list[str]:
    lines: list[str] = [
        "## Discovery tier rules (canonical)",
        "",
        "Single definition for **all** matrices (A0–A5, B0–B4, future presets), vs the **baseline folder** for this run.",
        "",
        "### Relax-candidate (strong signal — still not promotion)",
        "",
        "Requires **all** of:",
        "",
    ]
    relax = summary.get("relax_candidate") or {}
    for k, v in relax.items():
        lines.append(f"- **{k}:** {v}")
    lines.extend(
        [
            "",
            "Includes **max drawdown** and **confidence** vs baseline so relax-tier cannot be earned on throughput + PF alone.",
            "",
            "### Watchlist (weak signal — not promotion)",
            "",
        ]
    )
    wl = summary.get("watchlist") or {}
    for k, v in wl.items():
        if k == "notes":
            continue
        lines.append(f"- **{k}:** {v}")
    if wl.get("notes"):
        lines.extend(["", f"- **Note:** {wl['notes']}", ""])
    return lines


def _clustered_variant_sets(clusters: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    relax_v: set[str] = set()
    watch_v: set[str] = set()
    for cl in clusters:
        tier = cl.get("tier")
        vs = cl.get("variants") or []
        if len(vs) < 2:
            continue
        if tier == "relax_candidate":
            relax_v.update(vs)
        elif tier == "watchlist":
            watch_v.update(vs)
    return relax_v, watch_v


def _render_discovery_clusters_md(c: dict[str, Any]) -> list[str]:
    clusters = c.get("discovery_clusters") or []
    lines: list[str] = [
        "",
        "## Discovery Clusters (interpretive)",
        "",
        "Objective **tiers** are unchanged; this section only **summarizes** variants that landed in the "
        "same tier with **near-identical** headline metrics (`total_trades`, `expectancy_r`, `profit_factor`, "
        "`max_drawdown_r`). "
        "**Does not** affect `promotion_decision.json` or tier classification.",
        "",
    ]
    if not clusters:
        lines.extend(["*No multi-variant metric clusters in this run.*", ""])
        return lines

    for cl in clusters:
        tier = str(cl.get("tier", "")).replace("_", " ").title()
        vfs = cl.get("variants") or []
        pref = cl.get("preferred_next_test") or ""
        met = cl.get("representative_metrics") or {}
        nick = " / ".join(f"`{v}`" for v in vfs)
        pk = _vf_to_matrix_style_key(pref) if pref else ""
        lines.extend(
            [
                f"### {tier} cluster",
                "",
                f"- **Variants:** {nick}",
                f"- **Preferred next test:** **`{pk}`** (`{pref}`) — lowest heuristic config-delta rank in this cluster "
                "(single-knob variants preferred over combined relaxations when metrics tie; see "
                "`VARIANT_CONFIG_DELTA_RANK` in `quantmetrics_os/scripts/discovery_clusters.py`).",
                f"- **Representative metrics:** trades={met.get('total_trades')}, exp_R={met.get('expectancy_r')}, "
                f"PF={met.get('profit_factor')}, max_dd_R={met.get('max_drawdown_r')}",
                f"- **Rationale:** {cl.get('rationale', '')}",
                "",
            ]
        )
    return lines


def _render_discovery_watchlist_md_collapsed(c: dict[str, Any]) -> list[str]:
    wby = c.get("watchlist_by_variant") or {}
    clusters = c.get("discovery_clusters") or []
    _, cw = _clustered_variant_sets(clusters)
    lines: list[str] = [
        "",
        "## Discovery Watchlist (this run)",
        "",
        "Full per-variant strings remain in **JSON** under `conclusions.guards_to_watchlist` and "
        "`conclusions.watchlist_by_variant`. Below, **multi-variant clusters** are shown once for readability.",
        "",
    ]
    if not wby:
        lines.extend(["- (none)", ""])
        return lines

    unclustered = sorted(vf for vf in wby if vf not in cw)
    if unclustered:
        lines.append("**Unclustered watchlist:**")
        for vf in unclustered:
            lines.append(f"- {wby[vf]}")
        lines.append("")
    if cw:
        lines.append(
            "**Clustered watchlist:** summarized under **Discovery Clusters** above "
            "(same trades / exp_R / PF / max_dd_R bucket)."
        )
        lines.append("")
    return lines


def render_compare_md(payload: dict[str, Any]) -> str:
    lines = [
        "# THROUGHPUT COMPARE",
        "",
        f"*Generated (UTC): {payload.get('generated_at_utc')}*",
        "",
        f"- experiment_id: `{payload.get('experiment_id')}`",
        f"- baseline folder: `{payload.get('baseline_variant_folder')}`",
        "",
        "**Relax-candidate ≠ promotion.** **Watchlist ≠ promotion.** The production promotion gate is unchanged.",
        "",
        "## Variant table",
        "",
        "| Variant | trades | raw | after_filters | executed | kill_ratio | exp_R | PF | max_dd_R | prot.guard | conf | promote | Δtrades | Δexp | ΔPF | dd/baseline |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in payload.get("variants", []):
        lines.append(
            "| {v} | {t} | {raw} | {aft} | {exe} | {kill} | {exp} | {pf} | {dd} | {pg} | {cf} | {pr} | {dt} | {de} | {dpf} | {ddr} |".format(
                v=r.get("variant"),
                t=r.get("total_trades"),
                raw=r.get("raw_signals_detected"),
                aft=r.get("signals_after_filters"),
                exe=r.get("signals_executed"),
                kill=r.get("filter_kill_ratio"),
                exp=r.get("expectancy_r"),
                pf=r.get("profit_factor"),
                dd=r.get("max_drawdown_r"),
                pg=r.get("protective_guard_detected"),
                cf=r.get("confidence"),
                pr=r.get("promotion_decision"),
                dt=r.get("delta_trades_vs_baseline"),
                de=r.get("delta_expectancy_vs_baseline"),
                dpf=r.get("delta_pf_vs_baseline"),
                ddr=r.get("dd_worsen_ratio_vs_baseline"),
            )
        )

    summary = payload.get("conclusions", {}).get("discovery_rule_summary") or {}
    lines.append("")
    lines.extend(_render_discovery_rule_summary_md(summary))

    c = payload.get("conclusions", {})
    lines.extend(
        [
            "",
            "## Conclusions (automated triage)",
            "",
            f"- best_throughput_variant: `{c.get('best_throughput_variant')}`",
            f"- best_quality_variant: `{c.get('best_quality_variant')}`",
            f"- best_balanced_variant: `{c.get('best_balanced_variant')}`",
            "",
            "### guards_to_keep",
            "",
        ]
    )
    keep_items = c.get("guards_to_keep") or []
    if not keep_items:
        lines.append("- (none)")
    else:
        for item in keep_items:
            lines.append(f"- {item}")
    lines.extend(["", "### guards_to_relax_candidate", ""])
    relax_items = c.get("guards_to_relax_candidate") or []
    if not relax_items:
        lines.append("- (none)")
    else:
        for item in relax_items:
            lines.append(f"- {item}")
    lines.extend(_render_discovery_clusters_md(c))
    lines.extend(_render_discovery_watchlist_md_collapsed(c))
    lines.extend(["### guards_to_investigate (top)", ""])
    inv_items = c.get("guards_to_investigate") or []
    if not inv_items:
        lines.append("- (none)")
    else:
        for item in inv_items:
            lines.append(f"- {item}")
    lines.extend(["", "### guards_to_remove_candidate", ""])
    rem_items = c.get("guards_to_remove_candidate") or []
    if not rem_items:
        lines.append("- (none — removal requires explicit risk review)")
    else:
        for item in rem_items:
            lines.append(f"- {item}")
    lines.extend(["", "### Notes", ""])
    for note in c.get("notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare throughput matrix variants")
    parser.add_argument(
        "--experiment-root",
        type=Path,
        required=True,
        help="Path to quantmetrics_os/runs/<experiment_id>/",
    )
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--baseline-folder", default="a0_baseline")
    parser.add_argument(
        "--max-dd-worsen-ratio",
        type=float,
        default=dt.DEFAULT_MAX_DD_WORSEN_RATIO,
        help="Relax-candidate: variant max_dd_R / baseline max_dd_R must be <= this (default 1.2)",
    )
    args = parser.parse_args()

    root = args.experiment_root.expanduser().resolve()
    payload = build_compare_payload(
        experiment_id=args.experiment_id,
        experiment_root=root,
        baseline_folder=args.baseline_folder,
        max_dd_worsen_ratio=float(args.max_dd_worsen_ratio),
    )
    json_path = root / "THROUGHPUT_COMPARE.json"
    md_path = root / "THROUGHPUT_COMPARE.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_compare_md(payload), encoding="utf-8")
    print(str(json_path))
    print(str(md_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
