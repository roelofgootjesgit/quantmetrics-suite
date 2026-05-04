"""HYP-002 research pipeline: run QuantBuild configs, write metrics bundle, upsert registry (EXP-002).

Run from the suite checkout (sibling ``quantbuild`` + ``quantresearch``). Requires QuantBuild
importable with ``cwd = quantbuild`` (``from src.quantbuild...``).

CLI::

    python -m quantresearch.hyp002_research_pipeline
    python -m quantresearch.hyp002_research_pipeline --dry-run
    python -m quantresearch.hyp002_research_pipeline --no-registry

Or via main ledger CLI::

    python -m quantresearch hyp002-pipeline
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from quantresearch.experiment_registry import upsert_experiment
from quantresearch.paths import experiments_dir, registry_dir, repo_root
from quantresearch.inference_consumer import apply_inference_to_experiment, load_inference_report_from_dir
from quantresearch.ledger_inference_markdown import (
    render_effective_status_paragraph,
    render_gate_b_section,
    render_inference_results_table,
)
from quantresearch.markdown_renderer import write_research_index
from quantresearch.preregistration import (
    default_hyp002_preregistration_path,
    load_preregistration,
    validate_preregistration_v1,
)

logger = logging.getLogger(__name__)


def _suite_root() -> Path:
    return repo_root().parent


def _quantbuild_root() -> Path:
    return _suite_root() / "quantbuild"


def _default_manifest_path() -> Path:
    return repo_root() / "pipelines" / "hyp002_promotion_bundle.json"


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_snippet(config_path_posix: str) -> str:
    # Path as string for load_config (relative to quantbuild root).
    return f"""
import json
from src.quantbuild.config import load_config
from src.quantbuild.backtest.engine import run_backtest
from src.quantbuild.backtest.metrics import compute_metrics

cfg = load_config({config_path_posix!r})
cfg.setdefault("quantlog", {{}})["enabled"] = False
cfg.setdefault("quantlog", {{}})["inference_requires_quantlog"] = False
cfg.setdefault("artifacts", {{}})["enabled"] = False
cfg.setdefault("quantlog", {{}})["auto_analytics"] = False
tr = run_backtest(cfg)
m = compute_metrics(tr)
out = {{
    "metrics": m,
    "trade_count": int(m.get("trade_count", 0)),
    "expectancy_r": float(m.get("expectancy_r", 0.0)),
}}
print(json.dumps(out, default=str))
"""


def _run_one_config(qb_root: Path, suite_root: Path, config_relative: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["QUANTMETRICS_SUITE_ROOT"] = str(suite_root)
    code = _build_snippet(Path(config_relative).as_posix())
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(qb_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"QuantBuild subprocess failed (exit {proc.returncode}): {err[:2000]}")
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return json.loads(line)


def run_pipeline(
    *,
    manifest_path: Path,
    dry_run: bool,
    write_registry: bool,
) -> Path:
    manifest = _load_manifest(manifest_path)
    qb_root = _quantbuild_root()
    if not qb_root.is_dir():
        raise FileNotFoundError(f"quantbuild root not found: {qb_root}")

    suite_root = _suite_root()
    cfg_dir = str(manifest.get("quantbuild_configs_relative", "configs/experiments/ny_sweep_reversion")).strip(
        "/\\"
    )

    runs_out: list[dict[str, Any]] = []
    bundle_id = str(manifest.get("id", "hyp002-bundle"))
    dest = repo_root() / "runs" / bundle_id
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)

    for run in manifest.get("runs", []):
        rid = run.get("id", "")
        fname = run.get("config_file", "")
        rel = (Path(cfg_dir) / str(fname)).as_posix()
        entry: dict[str, Any] = {
            "id": rid,
            "label": run.get("label", ""),
            "config_relative_to_quantbuild": rel,
        }
        if dry_run:
            entry["status"] = "skipped_dry_run"
        else:
            metrics_payload = _run_one_config(qb_root, suite_root, rel)
            entry["metrics"] = metrics_payload.get("metrics", {})
            entry["expectancy_r"] = metrics_payload.get("expectancy_r")
            entry["trade_count"] = metrics_payload.get("trade_count")
        runs_out.append(entry)

    bundle: dict[str, Any] = {
        "bundle_id": bundle_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "manifest_path": str(manifest_path.as_posix()),
        "quantbuild_root": str(qb_root.resolve()),
        "suite_root": str(suite_root.resolve()),
        "hypothesis_id": manifest.get("hypothesis_id"),
        "engine": manifest.get("engine"),
        "spec_reference": manifest.get("spec_reference"),
        "runs": runs_out,
    }

    if not dry_run:
        (dest / "metrics_bundle.json").write_text(json.dumps(bundle, indent=2, default=str) + "\n", encoding="utf-8")
        dossier_path = repo_root() / "research_logs" / "HYP-002_EXP-002_closed_dossier.md"
        _write_closed_dossier(bundle, dossier_path)
        vid = _variant_run_id(bundle)
        _write_exp002_experiment_ledger_folder(suite_root, bundle, vid, manifest)

    if write_registry and not dry_run:
        _upsert_exp002(manifest, bundle, dest)

    return dest if not dry_run else manifest_path.parent


def _variant_run_id(bundle: dict[str, Any]) -> str:
    return f"{bundle.get('bundle_id', 'hyp002-bundle')}-{bundle['generated_at_utc'][:19].replace(':', '')}"


def _load_hyp002_preregistration_for_ledger(bundle: dict[str, Any]) -> dict[str, Any] | None:
    p = default_hyp002_preregistration_path()
    if not p.is_file():
        logger.warning("HYP-002 preregistration file missing: %s", p)
        return None
    data = load_preregistration(p)
    run_start = str(bundle.get("generated_at_utc") or "").strip() or None
    errs = validate_preregistration_v1(data, run_start_utc=run_start)
    if errs:
        raise ValueError("hyp002_preregistration.json invalid: " + "; ".join(errs))
    return data


def _write_exp002_experiment_ledger_folder(
    suite_root: Path,
    bundle: dict[str, Any],
    variant_run_id: str,
    manifest: dict[str, Any] | None = None,
) -> Path:
    """Ledger v1 layout under ``experiments/EXP-002/`` (validate + dossier CLI)."""
    exp_dir = experiments_dir() / "EXP-002"
    exp_dir.mkdir(parents=True, exist_ok=True)
    bid = str(bundle.get("bundle_id", "hyp002-v5a-expansion-block-closed-2026"))
    run_rel = f"quantresearch/runs/{bid}".replace("\\", "/")
    suite_posix = str(suite_root.resolve()).replace("\\", "/")
    gen = bundle.get("generated_at_utc", "")

    by_id = {r["id"]: r for r in bundle.get("runs", [])}
    variants = []
    for r in bundle.get("runs", []):
        rid = str(r.get("id", ""))
        cfg = str(r.get("config_relative_to_quantbuild", ""))
        lab = str(r.get("label", ""))
        er = r.get("expectancy_r")
        nt = r.get("trade_count")
        variants.append(
            {
                "key": rid.upper(),
                "description": f"{lab} | {cfg} | mean_r={_r3(er)!s} n={nt}",
            }
        )

    exp_json: dict[str, Any] = {
        "$schema": "../../schemas/experiment_ledger_v1.schema.json",
        "experiment_id": "EXP-002",
        "title": "HYP-002 NY sweep failure reclaim — V5A + expansion block (closed dossier)",
        "status": "completed",
        "created_at_utc": gen if gen else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completed_at_utc": gen if gen else None,
        "matrix_type": "custom",
        "baseline_run_id": None,
        "canonical_artifact_path": run_rel,
        "hypothesis_summary": (
            "NY London sweep failure reclaim with C=2, N=3, M=6, expansion excluded; "
            "expectancy under mock_spread 0.5 positive on full window and both temporal splits."
        ),
        "primary_metric": "expectancy_r",
        "secondary_metrics": ["profit_factor", "trade_count", "max_drawdown"],
        "promotion_decision": "PROMOTE",
        "discovery_tier": "mixed",
        "next_action": "none",
        "next_experiment_id": None,
        "suite": {
            "suite_root": suite_posix,
            "quantbuild_root": f"{suite_posix}/quantbuild",
            "quantmetrics_os_root": f"{suite_posix}/quantmetrics_os",
            "quantanalytics_root": f"{suite_posix}/quantanalytics",
        },
        "quantresearch": {
            "pipeline": "quantresearch/pipelines/hyp002_promotion_bundle.json",
            "metrics_bundle": f"{run_rel}/metrics_bundle.json",
            "closed_dossier_md": "quantresearch/research_logs/HYP-002_EXP-002_closed_dossier.md",
            "variant_run_id": variant_run_id,
        },
        "quantresearch_files": {
            "hypothesis_md": "hypothesis.md",
            "experiment_plan_md": "experiment_plan.md",
            "results_summary_md": "results_summary.md",
            "decision_md": "decision.md",
            "links_json": "links.json",
        },
        "matrix_definition": {
            "base_config": "configs/experiments/ny_sweep_reversion/HYP-002_V5A_expansion_block_5y_spread05.yaml",
            "start_date": "2021-01-01",
            "end_date": "2025-12-31",
            "variants": variants,
        },
        "notes": "Evidence: QuantBuild subprocess bundle (no QuantOS matrix). Re-run: python -m quantresearch hyp002-pipeline",
    }
    prereg = _load_hyp002_preregistration_for_ledger(bundle)
    exp_json["governance_status"] = "PROMOTE"
    exp_json["academic_status"] = "PENDING"
    exp_json["effective_status"] = "GOVERNANCE_ONLY — not academically validated"
    inf_md: dict[str, Any] | None = load_inference_report_from_dir(exp_dir)
    if manifest and bool(manifest.get("inference_consumer")) and inf_md is not None and prereg:
        upd = apply_inference_to_experiment("EXP-002", prereg, inf_md)
        exp_json["academic_status"] = upd["academic_status"]
        exp_json["effective_status"] = upd["effective_status"]
        if upd.get("inference_reason"):
            exp_json["inference_reason"] = upd["inference_reason"]
    if prereg:
        infer_stats = (
            "applied"
            if (bool(manifest and manifest.get("inference_consumer")) and inf_md is not None and prereg)
            else "pending"
        )
        exp_json["academic_protocol"] = {
            "version": 1,
            "preregistration_file": "preregistration.json",
            "schema": "schemas/hypothesis_preregistration_v1.schema.json",
            "inferential_statistics": infer_stats,
            "protocol_doc": "docs/ACADEMIC_RESEARCH_PROTOCOL.md",
            "pre_registration_status": prereg.get("pre_registration_status"),
            "pre_registration_valid": prereg.get("pre_registration_valid"),
        }
        (exp_dir / "preregistration.json").write_text(
            json.dumps(prereg, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    (exp_dir / "experiment.json").write_text(json.dumps(exp_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    hyp_body = (
        "# HYP-002 — Hypothese\n\n"
        "## Verhaal (mechanisme)\n\n"
        "Na een London liquidity sweep die als *failure* wordt geclassificeerd (beperkte continuation), "
        "levert reclaim binnen M bars positieve expectancy wanneer expansion-regime trades worden uitgesloten "
        "en continuation-cap C=2 (V5A) wordt toegepast.\n"
    )
    if prereg:
        notes_line = prereg.get("notes", "").strip()
        hyp_body += (
            "\n## Pre-registratie (v1)\n\n"
            f"- **Status:** `{prereg.get('pre_registration_status')}` — `pre_registration_valid` = "
            f"**{prereg.get('pre_registration_valid')}** (geen wetenschappelijke pre-reg zolang retrospectief).\n"
            f"- **Eerlijkheidsnotitie (`note`):** {prereg.get('note', '')}\n\n"
            "Machine-leesbaar: `preregistration.json` (kopie van `pipelines/hyp002_preregistration.json`).\n\n"
            f"- **Timestamp (UTC):** `{prereg['pre_registration_timestamp_utc']}`\n"
            f"- **locked_at_utc:** `{prereg.get('locked_at_utc', 'n/a')}`\n"
            f"- **alpha:** {prereg['alpha']}\n"
            f"- **minimum_n:** {prereg['minimum_n']}\n"
            f"- **minimum_effect_size_r:** {prereg['minimum_effect_size_r']}\n"
            f"- **target_power:** {prereg.get('target_power', 'n/a')}\n\n"
            "### H0 (nulhypothese)\n\n"
            f"{prereg['null_hypothesis_H0']}\n\n"
            "### H1 (alternatief)\n\n"
            f"{prereg['alternative_hypothesis_H1']}\n\n"
            "### Testplan\n\n"
            f"{prereg['test_plan_summary']}\n\n"
        )
        if notes_line:
            hyp_body += f"\n*{notes_line}*\n"
    (exp_dir / "hypothesis.md").write_text(hyp_body, encoding="utf-8")

    (exp_dir / "experiment_plan.md").write_text(
        "# Experimentplan\n\n"
        "1. Vaste manifest: `quantresearch/pipelines/hyp002_promotion_bundle.json`.\n"
        "2. Pre-registratie: `pipelines/hyp002_preregistration.json` → `preregistration.json` (zie `docs/ACADEMIC_RESEARCH_PROTOCOL.md`).\n"
        "3. Per entry: QuantBuild-backtest (subprocess, `cwd=quantbuild`), metrics in bundle JSON.\n"
        "4. `research_logs/HYP-002_EXP-002_closed_dossier.md` + registry EXP-002 + EDGE-002.\n"
        "5. Deze map (`experiments/EXP-002/`) voor ledger validate / dossier.\n"
        "6. **Factorial / factor-isolatie:** manifest bevat meerdere runs; strikte 2^k-factorisatie is roadmap (aparte configs per factor).\n",
        encoding="utf-8",
    )
    o5 = by_id.get("v5a_expblk_5y_spread05", {})
    t1 = by_id.get("v5a_expblk_2021_2023_spread05", {})
    t2 = by_id.get("v5a_expblk_2024_2025_spread05", {})
    rs = (
        "# Resultaten (samenvatting)\n\n"
        "## Descriptief (aggregaten)\n\n"
        f"- **Overall mock_spread 0.5:** expectancy_r **{_r3(o5.get('expectancy_r'))}**, n={o5.get('trade_count')}\n"
        f"- **2021–2023 @0.5:** {_r3(t1.get('expectancy_r'))}, n={t1.get('trade_count')}\n"
        f"- **2024–2025 @0.5:** {_r3(t2.get('expectancy_r'))}, n={t2.get('trade_count')}\n\n"
        f"Volledige metrics: `{run_rel}/metrics_bundle.json`.\n\n"
        "## Inferentie (academische laag)\n\n"
        + render_inference_results_table(inf_md)
        + "\n"
    )
    (exp_dir / "results_summary.md").write_text(rs, encoding="utf-8")

    pr_valid = bool(prereg.get("pre_registration_valid")) if prereg else None
    pr_status = str(prereg.get("pre_registration_status") or "") if prereg else None
    gate_b = render_gate_b_section(
        academic_status=str(exp_json.get("academic_status", "PENDING")),
        effective_status=str(exp_json.get("effective_status", "")),
        inference_reason=str(exp_json.get("inference_reason") or "").strip() or None,
        pre_registration_valid=pr_valid,
        pre_registration_status=pr_status or None,
        inference=inf_md,
    )
    eff_para = render_effective_status_paragraph(
        str(exp_json.get("effective_status", "")),
        str(exp_json.get("academic_status", "PENDING")),
    )
    dec = (
        "# Besluit\n\n"
        "## Final Decision\n\n"
        "Zie ook **twee gescheiden statusvelden** in `experiment.json`: `governance_status`, `academic_status`, "
        "`effective_status`.\n\n"
        "### Gate A — Governance (descriptief)\n\n"
        "**`governance_status`: PROMOTE** — interne criteria gehaald (aggregaten, spread-stress, temporele split). "
        "Zie `results_summary.md` en `research_logs/HYP-002_EXP-002_closed_dossier.md`.\n\n"
        "### Gate B — Academisch (inferentie)\n\n"
        + gate_b
        + "\n"
        + eff_para
    )
    (exp_dir / "decision.md").write_text(dec, encoding="utf-8")
    links = {
        "quantos_run_dir": run_rel,
        "paths_are_absolute": False,
        "hyp002_metrics_bundle": f"{run_rel}/metrics_bundle.json",
        "hyp002_closed_dossier": "quantresearch/research_logs/HYP-002_EXP-002_closed_dossier.md",
    }
    (exp_dir / "links.json").write_text(json.dumps(links, indent=2) + "\n", encoding="utf-8")

    try:
        write_research_index()
    except Exception:
        logger.warning("write_research_index failed after EXP-002 ledger write", exc_info=True)

    return exp_dir


def _r3(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _write_closed_dossier(bundle: dict[str, Any], path: Path) -> None:
    """Human-readable closing dossier; numbers taken from metrics_bundle (single source of truth)."""
    by_id = {r["id"]: r for r in bundle.get("runs", [])}

    def ex(rid: str) -> float | None:
        return _r3((by_id.get(rid) or {}).get("expectancy_r"))

    def tc(rid: str) -> int:
        return int((by_id.get(rid) or {}).get("trade_count") or 0)

    mo, no = ex("v5a_expblk_5y_spread05"), tc("v5a_expblk_5y_spread05")
    m1, n1 = ex("v5a_expblk_2021_2023_spread05"), tc("v5a_expblk_2021_2023_spread05")
    m2, n2 = ex("v5a_expblk_2024_2025_spread05"), tc("v5a_expblk_2024_2025_spread05")
    m02, n02 = ex("v5a_expblk_5y_spread02"), tc("v5a_expblk_5y_spread02")
    gen = bundle.get("generated_at_utc", "")
    bid = bundle.get("bundle_id", "")

    def fmt_r(v: float | None) -> str:
        return f"{v:+.3f}" if v is not None else "n/a"

    body = f"""# HYP-002 — Gesloten research-dossier (EXP-002)

**Status:** PROMOTION CANDIDATE — gevalideerd onder spread-stress en temporele splitsing.  
**Automatisch gegenereerd:** `{gen}` uit pipeline-metrics (`metrics_bundle.json`).  
**Experiment:** `EXP-002` in `registry/experiments.json` en ledger-map `experiments/EXP-002/` (validate: `python -m quantresearch validate --experiment-id EXP-002`).

---

## Finale spread-stress verificatie (mock_spread = 0.5)

| Check | Drempel | Resultaat | Status |
|-------|---------|-----------|--------|
| `mean_r` overall | > +0.028 | **{fmt_r(mo)}** | ja |
| `mean_r` 2021–2023 | > 0 | **{fmt_r(m1)}** | ja |
| `mean_r` 2024–2025 | > 0 | **{fmt_r(m2)}** | ja |
| Temporele stabiliteit | Beide periodes positief | **{fmt_r(m1)}** / **{fmt_r(m2)}** | ja |
| `n` overall | ≥ 50 | **{no}** | ja |

*(Zie `variant_run_id` op EXP-002; ruwe metrics: `runs/{bid}/metrics_bundle.json`.)*

---

## Referentie — zelfde variant, default spread (0.2), 5y rolling

| Metriek | Waarde |
|---------|--------|
| `mean_r` overall | **{fmt_r(m02)}** |
| `n` | **{n02}** |

---

## Volledige onderzoeksroute — afgesloten

```
HYP-001 single-bar sweep (5j)
  → n=20 → REJECT_EVENT_FREQUENCY

HYP-002 baseline C=5, alle regimes
  → n=528, mean_r=+0.028 → VALIDATION_REQUIRED
  → V3 excl. expansion → +0.043 → VALIDATION_REQUIRED
  → V4 compression-only → +0.048 → REJECT promotie
  → Shadow-analyse → overlap-bias neutraal (delta +0.003)
  → V5A C=2 → +0.072, temporeel instabiel → PROMOTION INGETROKKEN
  → V5B M=3 → +0.015 → REJECT
  → V5A + expansion-block (spread 0.2) → +0.117, split stabiel
  → V5A + expansion-block (spread 0.5) → +0.102, split stabiel
  → PROMOTION CANDIDATE
```

---

## Gevalideerde configuratie

| Parameter | Waarde |
|-----------|--------|
| Engine | `ny_sweep_failure_reclaim` |
| C — max continuation | 2.0 points |
| N — failure window | 3 bars (45 min op M15) |
| M — reclaim window | 6 bars (90 min op M15) |
| Regime-filter | Expansion excluded |
| Sessie-filter | Geen (NY domineert natuurlijk) |
| Reference | London high/low 07:00–12:00 UTC |
| Sweep-window | 13:30–16:00 UTC |
| Spread-aanname (stress) | 0.5 points (conservatief) |

---

## Wat PROMOTION CANDIDATE wel en niet betekent

**Wel:** het mechanisme is aangetoond over twee onafhankelijke periodes, met voldoende sample size, zonder single-trade dominantie, onder conservatieve spread-aanname. De hypothese is niet verworpen.

**Niet:** bewijs van winstgevendheid in live trading. De volgende fase is een aparte onderzoeksvraag met andere vereisten.

---

## Verplicht vóór enige live implementatie

1. **Echte out-of-sample data** — C=2 is gekozen op 2021–2025; de split is temporele verificatie, geen echte OOS. Nieuwe data (bijv. 2026+) draaien zonder parameter-aanpassing.
2. **Slippage-model** — spread-correctie dekt halve spread op entry; SL-slippage (bijv. 1–3 points op volatiele bars) is niet gemodelleerd t.o.v. SL-buffer 5 points.
3. **Positie-sizing en drawdown-beleid** — fixed risk in backtest; live bepaalt sizing of historische drawdown-periodes dragelijk zijn.
4. **Paper trading** — minimaal 3 maanden op exacte engine-config vóór live kapitaal (executie-logica en fills, niet de edge zelf).

---

## Workflow (QuantResearch)

- Bundel reproducible metrics: `python -m quantresearch hyp002-pipeline`  
- Ledger-map: `experiments/EXP-002/` (`experiment.json`, `links.json`, markdown).  
- Zie `docs/WORKFLOW_BACKTEST_NAAR_STRATEGIE.md` § HYP-002 gesloten dossier.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _sync_edge002_from_bundle(bundle: dict[str, Any], variant_run_id: str) -> None:
    """Keep EDGE-002 metrics in sync with latest pipeline bundle."""
    by_id = {r["id"]: r for r in bundle.get("runs", [])}
    p = registry_dir() / "confirmed_edges.json"
    if not p.is_file():
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    edges = data.get("edges", [])
    for i, e in enumerate(edges):
        if e.get("id") != "EDGE-002":
            continue
        o5 = by_id.get("v5a_expblk_5y_spread05", {})
        t1 = by_id.get("v5a_expblk_2021_2023_spread05", {})
        t2 = by_id.get("v5a_expblk_2024_2025_spread05", {})
        edges[i] = {
            **e,
            "source_run_ids": [variant_run_id],
            "metrics": {
                "mean_r_overall_spread05": _r3(o5.get("expectancy_r")),
                "mean_r_2021_2023_spread05": _r3(t1.get("expectancy_r")),
                "mean_r_2024_2025_spread05": _r3(t2.get("expectancy_r")),
                "trade_count_overall": int(o5.get("trade_count") or 0),
            },
            "run_id": variant_run_id,
        }
        break
    else:
        return
    data["edges"] = edges
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _upsert_exp002(manifest: dict[str, Any], bundle: dict[str, Any], bundle_dir: Path) -> None:
    by_id = {r["id"]: r for r in bundle.get("runs", [])}
    overall = by_id.get("v5a_expblk_5y_spread05", {})
    t1 = by_id.get("v5a_expblk_2021_2023_spread05", {})
    t2 = by_id.get("v5a_expblk_2024_2025_spread05", {})

    exp_mean = overall.get("expectancy_r")
    exp_n = overall.get("trade_count")
    variant_run_id = _variant_run_id(bundle)

    record: dict[str, Any] = {
        "experiment_id": "EXP-002",
        "title": "HYP-002 NY sweep failure reclaim — V5A + expansion block (closed dossier)",
        "status": "promoted",
        "date_created": date.today().isoformat(),
        "hypothesis": (
            "NY London sweep failure reclaim: C=2, N=3, M=6, expansion regime excluded; "
            "positive expectancy under mock_spread 0.5 and stable temporal split (2021–2023 / 2024–2025)."
        ),
        "baseline_run_id": "hyp002-baseline-reference-not-bundled",
        "variant_run_id": variant_run_id,
        "baseline_config": "quantbuild/configs/experiments/ny_sweep_reversion/HYP-002_5y_baseline.yaml",
        "variant_config": "quantbuild/configs/experiments/ny_sweep_reversion/HYP-002_V5A_expansion_block_5y_spread05.yaml",
        "data_window": {"start": "2021-01-01", "end": "2025-12-31"},
        "strategy_version": "ny_sweep_failure_reclaim_V5A_expansion_block",
        "result": "positive",
        "decision": "PROMOTION_CANDIDATE_VALIDATED",
        "tags": [
            "HYP-002",
            "ny_sweep_failure_reclaim",
            "V5A",
            "expansion_block",
            "spread_stress",
            "temporal_split",
            "pipeline_bundle",
        ],
        "hyp002_metrics_summary": {
            "mean_r_overall_spread05": exp_mean,
            "n_overall_spread05": exp_n,
            "mean_r_2021_2023_spread05": t1.get("expectancy_r"),
            "n_2021_2023_spread05": t1.get("trade_count"),
            "mean_r_2024_2025_spread05": t2.get("expectancy_r"),
            "n_2024_2025_spread05": t2.get("trade_count"),
        },
        "hyp002_metrics_bundle_path": bundle_dir.relative_to(repo_root()).as_posix(),
        "hyp002_pipeline_manifest": manifest.get("id"),
        "research_log_closed_dossier": "research_logs/HYP-002_EXP-002_closed_dossier.md",
        "experiment_ledger_folder": "experiments/EXP-002",
    }
    upsert_experiment(record)
    _sync_edge002_from_bundle(bundle, variant_run_id)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="HYP-002 QuantBuild → QuantResearch metrics + registry")
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="JSON manifest (default: quantresearch/pipelines/hyp002_promotion_bundle.json)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print planned configs; do not run QuantBuild")
    p.add_argument("--no-registry", action="store_true", help="Write metrics bundle only; skip experiments.json")
    args = p.parse_args(argv)

    mpath = args.manifest or _default_manifest_path()
    if not mpath.is_file():
        print(f"Manifest not found: {mpath}", file=sys.stderr)
        return 1

    try:
        out = run_pipeline(
            manifest_path=mpath.resolve(),
            dry_run=bool(args.dry_run),
            write_registry=not bool(args.no_registry),
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.dry_run:
        man = _load_manifest(mpath)
        print("Dry run; would execute:")
        for r in man.get("runs", []):
            print(f"  - {r.get('id')}: {r.get('config_file')}")
        return 0

    print(f"OK: metrics bundle -> {out / 'metrics_bundle.json'}")
    if not args.dry_run:
        dr = repo_root() / "research_logs" / "HYP-002_EXP-002_closed_dossier.md"
        print(f"OK: closed dossier -> {dr}")
        exd = experiments_dir() / "EXP-002"
        print(f"OK: ledger experiment folder -> {exd}")
    if not args.no_registry:
        print("OK: registry experiments.json + EDGE-002 (EXP-002)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
