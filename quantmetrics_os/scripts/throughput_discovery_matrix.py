#!/usr/bin/env python3
"""Throughput Discovery Experiment Matrix (QuantOS runner).

Runs a baseline QuantBuild backtest config plus controlled YAML variants, then for each run:
- consolidates QuantLog day JSONL into ``quantbuild/data/quantlog_events/runs/<run_id>.jsonl``
- bundles artifacts under ``quantmetrics_os/runs/<experiment>/<role>/``
- runs QuantAnalytics guard attribution CLI
- runs QuantOS promotion gate (optionally vs baseline drawdown)

This is orchestration + analysis wiring only: it does not mutate upstream QuantLog day files.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ExperimentSpec:
    key: str
    title: str
    filter_overrides: dict[str, bool] = field(default_factory=dict)
    config_overlay: dict[str, Any] = field(default_factory=dict)


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def _quantresearch_repo_root(qmos_root: Path, override: Path | None) -> Path:
    if override is not None:
        return override.expanduser().resolve()
    return (qmos_root.parent / "quantresearch").resolve()


def _run_quantresearch_cli(*, qr_root: Path, qr_argv: list[str]) -> None:
    """Run ``python -m quantresearch ...`` with repo on PYTHONPATH (dev layout)."""
    env = os.environ.copy()
    root_s = str(qr_root)
    env["QUANTRESEARCH_ROOT"] = root_s
    prev = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = f"{root_s}{os.pathsep}{prev}" if prev else root_s
    cmd = [sys.executable, "-m", "quantresearch", *qr_argv]
    _run(cmd, cwd=qr_root, env=env)


def _quantresearch_preflight(*, experiment_id: str, qr_root: Path) -> None:
    _run_quantresearch_cli(
        qr_root=qr_root,
        qr_argv=["validate", "--experiment-id", experiment_id, "--mode", "pre_run"],
    )


def _quantresearch_post_matrix_success(
    *,
    experiment_id: str,
    qr_root: Path,
    quantos_run_dir: Path,
) -> None:
    _run_quantresearch_cli(
        qr_root=qr_root,
        qr_argv=[
            "link-artifacts",
            "--experiment-id",
            experiment_id,
            "--quantos-run-dir",
            str(quantos_run_dir.resolve()),
        ],
    )
    _run_quantresearch_cli(
        qr_root=qr_root,
        qr_argv=["mark-completed", "--experiment-id", experiment_id],
    )
    _run_quantresearch_cli(qr_root=qr_root, qr_argv=["summarize"])


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _quantbuild_python(qb_root: Path) -> str:
    explicit = os.environ.get("PYTHON", "").strip()
    if explicit and Path(explicit).is_file():
        return explicit
    for candidate in (
        qb_root / ".venv" / "bin" / "python",
        qb_root / ".venv" / "Scripts" / "python.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dump_yaml(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _extract_run_id_from_log(log_path: Path) -> str | None:
    if not log_path.is_file():
        return None
    needle = "run_id="
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines[-400:]):
        idx = line.find(needle)
        if idx == -1:
            continue
        tail = line[idx + len(needle) :].strip()
        token = tail.split()[0]
        return token.strip()
    return None


def _consolidate_run_jsonl(*, quantbuild_root: Path, run_id: str) -> Path:
    root = quantbuild_root / "data" / "quantlog_events"
    out_dir = root / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_id}.jsonl"

    kept = 0
    scanned = 0
    with out_path.open("w", encoding="utf-8") as writer:
        # Day shards live at: data/quantlog_events/<YYYY-MM-DD>/quantbuild.jsonl
        candidates = sorted(root.glob("*/quantbuild.jsonl"))
        if not candidates:
            candidates = sorted(root.rglob("quantbuild.jsonl"))
        for day_jsonl in candidates:
            if "runs" in day_jsonl.parts:
                continue
            if not day_jsonl.is_file():
                continue
            scanned += 1
            with day_jsonl.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    if obj.get("run_id") == run_id:
                        writer.write(raw if raw.endswith("\n") else raw + "\n")
                        kept += 1

    if kept == 0:
        raise RuntimeError(
            f"Consolidation produced 0 events for run_id={run_id} (scanned_files={scanned}). "
            f"Expected day JSONL under: {root}"
        )
    return out_path


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print(f"+ {' '.join(cmd)}")
    print(f"(cwd) {cwd}")
    rc = int(subprocess.call(cmd, cwd=str(cwd), env=env))
    if rc != 0:
        raise RuntimeError(f"Command failed (exit {rc}): {' '.join(cmd)}")


def _run_backtest(
    *,
    qb_root: Path,
    python_exe: str,
    config_rel: str,
    start_date: str,
    end_date: str,
) -> Path:
    env = os.environ.copy()
    extra = str(qb_root.resolve())
    env["PYTHONPATH"] = f"{extra}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else extra

    cmd = [
        python_exe,
        "-m",
        "src.quantbuild.app",
        "--config",
        config_rel,
        "backtest",
        "--start-date",
        start_date,
        "--end-date",
        end_date,
    ]
    _run(cmd, cwd=qb_root, env=env)

    logs_dir = qb_root / "logs"
    candidates = sorted(logs_dir.glob("backtest_quantbuild_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError(f"No backtest log found under: {logs_dir}")
    latest = candidates[0]
    run_id = _extract_run_id_from_log(latest)
    if not run_id:
        raise RuntimeError(f"Could not parse run_id from log: {latest}")
    return latest


def _bundle_run(
    *,
    qmos_root: Path,
    qb_root: Path,
    experiment_id: str,
    role: str,
    run_id: str,
    config_path: Path,
) -> Path:
    script = qmos_root / "scripts" / "collect_run_artifact.py"
    cmd = [
        sys.executable,
        str(script),
        "--experiment-id",
        experiment_id,
        "--role",
        role,
        "--run-id",
        run_id,
        "--quantbuild-root",
        str(qb_root),
        "--quantmetrics-os-root",
        str(qmos_root),
        "--config-yaml",
        str(config_path),
    ]
    proc = subprocess.run(cmd, cwd=str(qmos_root), env=os.environ.copy(), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "collect_run_artifact failed:\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )
    dest_line = (proc.stdout or "").strip().splitlines()[-1].strip()
    return Path(dest_line)


def _run_guard_attribution(
    *,
    analytics_root: Path,
    runner_python: str,
    jsonl_path: Path,
    run_id: str,
    out_dir: Path,
) -> None:
    env = os.environ.copy()
    qa_root = Path(_require_env("QUANTANALYTICS_ROOT")).resolve()
    extra = str(qa_root / "src")
    env["PYTHONPATH"] = f"{extra}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else extra

    cmd = [
        runner_python,
        "-m",
        "quantanalytics.guard_attribution.cli",
        "--events",
        str(jsonl_path),
        "--run-id",
        run_id,
        "--out",
        str(out_dir),
    ]
    _run(cmd, cwd=qa_root, env=env)


def _run_promotion_gate(
    *,
    qmos_root: Path,
    analytics_dir: Path,
    baseline_analytics_dir: Path | None,
    max_dd_worsen_ratio: float,
) -> dict[str, Any]:
    script = qmos_root / "scripts" / "promotion_gate.py"
    cmd = [sys.executable, str(script), "--analytics-dir", str(analytics_dir)]
    if baseline_analytics_dir is not None:
        cmd.extend(
            [
                "--baseline-analytics-dir",
                str(baseline_analytics_dir),
                "--max-dd-worsen-ratio",
                str(max_dd_worsen_ratio),
            ]
        )
    proc = subprocess.run(cmd, cwd=str(qmos_root), env=os.environ.copy(), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "promotion_gate failed:\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}\n"
        )
    payload = json.loads((analytics_dir / "promotion_decision.json").read_text(encoding="utf-8"))
    return payload


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)  # type: ignore[assignment]
        else:
            out[k] = copy.deepcopy(v)
    return out


def _max_drawdown_r_from_stability_path(path: Path) -> float | None:
    if not path.is_file():
        return None
    stability = _read_json(path)
    values: list[float] = []
    for _dimension, rows in stability.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            dd = row.get("max_drawdown_r")
            if isinstance(dd, (int, float)):
                values.append(float(dd))
    if not values:
        return None
    return max(values)


def build_experiment_matrix() -> list[ExperimentSpec]:
    # Notes:
    # - All variants keep hard risk stack defaults enabled unless explicitly overridden here.
    # - "Relax" means disabling specific pipeline filters via ``filters:`` overrides.
    return [
        ExperimentSpec(
            key="A0_BASELINE",
            title="Baseline (control)",
            filter_overrides={},
        ),
        ExperimentSpec(
            key="A1_SESSION_RELAXED",
            title="Relax session filter only",
            filter_overrides={"session": False},
        ),
        ExperimentSpec(
            key="A2_REGIME_RELAXED",
            title="Relax regime filter only",
            filter_overrides={"regime": False},
        ),
        ExperimentSpec(
            key="A3_COOLDOWN_RELAXED",
            title="Relax cooldown only",
            filter_overrides={"cooldown": False},
        ),
        ExperimentSpec(
            key="A4_SESSION_REGIME_RELAXED",
            title="Relax session + regime",
            filter_overrides={"session": False, "regime": False},
        ),
        ExperimentSpec(
            key="A5_THROUGHPUT_DISCOVERY",
            title="Throughput discovery (non-risk filters relaxed)",
            filter_overrides={
                "session": False,
                "regime": False,
                "cooldown": False,
                "news": False,
                # keep: position_limit, daily_loss, spread, structure_h1_gate
            },
        ),
    ]


def build_session_relax_watchlist_matrix() -> list[ExperimentSpec]:
    """Follow-up matrix after throughput discovery watchlist flags session/expansion.

    B0: strict_prod_v2 control. B1–B3 adjust ``regime_profiles.expansion`` session gates only
    (trend + hard risk stack unchanged). B4 disables pipeline ``session`` filter (same idea as A1).

    Interpretation is documented in QuantResearch ``experiment_plan.md`` for the matching experiment_id.
    """
    return [
        ExperimentSpec(key="B0_BASELINE", title="Baseline (control)", filter_overrides={}),
        ExperimentSpec(
            key="B1_LONDON_ONLY_RELAXED",
            title="Expansion: allow London (add to expansion allowed_sessions)",
            filter_overrides={},
            config_overlay={
                "regime_profiles": {
                    "expansion": {
                        "allowed_sessions": ["London", "New York", "Overlap"],
                    }
                }
            },
        ),
        ExperimentSpec(
            key="B2_NY_ONLY_RELAXED",
            title="Expansion: NY-only list + relax min_hour_utc (set to 0)",
            filter_overrides={},
            config_overlay={
                "regime_profiles": {
                    "expansion": {
                        "allowed_sessions": ["New York"],
                        "min_hour_utc": 0,
                    }
                }
            },
        ),
        ExperimentSpec(
            key="B3_OVERLAP_RELAXED",
            title="Expansion: NY+Overlap with min_hour_utc relaxed to 0",
            filter_overrides={},
            config_overlay={
                "regime_profiles": {
                    "expansion": {
                        "allowed_sessions": ["New York", "Overlap"],
                        "min_hour_utc": 0,
                    }
                }
            },
        ),
        ExperimentSpec(
            key="B4_FULL_SESSION_RELAXED",
            title="Pipeline session filter off (full session relax vs baseline)",
            filter_overrides={"session": False},
        ),
    ]


def render_summary_md(
    *,
    generated_at_utc: str,
    experiment_id: str,
    base_config: Path,
    start_date: str,
    end_date: str,
    rows: list[dict[str, Any]],
    report_heading: str = "THROUGHPUT DISCOVERY SUMMARY",
) -> str:
    lines = [
        f"# {report_heading}",
        "",
        f"*Generated (UTC): {generated_at_utc}*",
        "",
        "## Matrix",
        "",
        f"- experiment_id: `{experiment_id}`",
        f"- base_config: `{base_config}`",
        f"- window: `{start_date}` .. `{end_date}`",
        "",
        "| Experiment | run_id | raw | after_filters | executed | kill_ratio | exec_ratio | trades | expectancy_R | PF | max_dd_R | promotion |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        tp = r.get("throughput", {})
        prom = r.get("promotion", {})
        metrics = prom.get("metrics", {})
        lines.append(
            "| {exp} | `{run}` | {raw} | {after} | {exe} | {kill} | {execr} | {trades} | {exp_r} | {pf} | {dd} | {promo} |".format(
                exp=r.get("experiment"),
                run=r.get("run_id"),
                raw=tp.get("raw_signals_detected"),
                after=tp.get("signals_after_filters"),
                exe=tp.get("signals_executed"),
                kill=_fmt_ratio(tp.get("filter_kill_ratio")),
                execr=_fmt_ratio(tp.get("execution_ratio")),
                trades=metrics.get("total_trades"),
                exp_r=_fmt_ratio(metrics.get("expectancy_r")),
                pf=_fmt_ratio(metrics.get("profit_factor")),
                dd=_fmt_ratio(r.get("max_drawdown_r")),
                promo=prom.get("promotion_decision"),
            )
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "Each variant is collected as its own role folder under:",
            "",
            f"- `{_repo_root_from_script() / 'runs' / experiment_id}/<ROLE>/`",
            "",
            "Each role folder should contain:",
            "",
            "- `analytics/throughput.json`",
            "- `analytics/guard_attribution.json`",
            "- `analytics/edge_verdict.json`",
            "- `analytics/promotion_decision.json`",
            "- `analytics/EDGE_REPORT.md`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt_ratio(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Throughput Discovery Experiment Matrix")
    parser.add_argument("--experiment-id", default="EXP-2025-throughput-discovery")
    parser.add_argument("--base-config", type=Path, required=True, help="YAML path relative to QUANTBUILD_ROOT")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument(
        "--matrix",
        choices=("throughput-discovery", "session-relax-watchlist"),
        default="throughput-discovery",
        help="Variant set: A0–A5 throughput matrix or B0–B4 session/expansion watchlist follow-up",
    )
    parser.add_argument(
        "--baseline-folder",
        default="",
        help="Role folder name for compare baseline (default: a0_baseline or b0_baseline from --matrix)",
    )
    parser.add_argument(
        "--max-dd-worsen-ratio",
        type=float,
        default=1.2,
        help="Fail drawdown check if variant max_dd_R > baseline * ratio (default: 1.2)",
    )
    parser.add_argument(
        "--quantresearch-root",
        type=Path,
        default=None,
        help="QuantResearch repository root (contains experiments/). Default: <suite>/quantresearch",
    )
    parser.add_argument(
        "--update-research-ledger",
        action="store_true",
        help="After a successful matrix + compare: link-artifacts, mark-completed, regenerate RESEARCH_LEDGER.md",
    )
    args = parser.parse_args()

    qmos_root = _repo_root_from_script()
    qb_root = Path(_require_env("QUANTBUILD_ROOT")).resolve()
    _require_env("QUANTANALYTICS_ROOT")

    qr_root = _quantresearch_repo_root(qmos_root, args.quantresearch_root)
    if not qr_root.is_dir():
        raise FileNotFoundError(
            f"QuantResearch root not found: {qr_root}. Set --quantresearch-root or place quantresearch next to quantmetrics_os."
        )
    _quantresearch_preflight(experiment_id=args.experiment_id, qr_root=qr_root)

    base_config_abs = (qb_root / args.base_config).resolve()
    if not base_config_abs.is_file():
        raise FileNotFoundError(f"Base config not found: {base_config_abs}")

    base_cfg = _load_yaml(base_config_abs)
    # QuantBuild loads configs relative to QUANTBUILD_ROOT; keep generated YAMLs inside quantbuild.
    gen_dir = qb_root / "configs" / "_throughput_discovery" / args.experiment_id
    gen_dir.mkdir(parents=True, exist_ok=True)

    qb_python = _quantbuild_python(qb_root)

    specs = (
        build_session_relax_watchlist_matrix()
        if args.matrix == "session-relax-watchlist"
        else build_experiment_matrix()
    )
    report_heading = (
        "SESSION RELAX WATCHLIST SUMMARY"
        if args.matrix == "session-relax-watchlist"
        else "THROUGHPUT DISCOVERY SUMMARY"
    )
    default_baseline = (
        "b0_baseline" if args.matrix == "session-relax-watchlist" else "a0_baseline"
    )
    compare_baseline_folder = (args.baseline_folder or default_baseline).strip()

    rows: list[dict[str, Any]] = []
    baseline_analytics: Path | None = None

    for spec in specs:
        variant_path = gen_dir / f"{spec.key}.yaml"
        merged = copy.deepcopy(base_cfg)
        if spec.filter_overrides:
            existing_filters = merged.get("filters") if isinstance(merged.get("filters"), dict) else {}
            merged["filters"] = {**existing_filters, **spec.filter_overrides}
        if spec.config_overlay:
            merged = _deep_merge(merged, spec.config_overlay)
        _dump_yaml(merged, variant_path)

        rel_config = str(variant_path.resolve().relative_to(qb_root)).replace("\\", "/")
        latest_log = _run_backtest(
            qb_root=qb_root,
            python_exe=qb_python,
            config_rel=rel_config,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        run_id = _extract_run_id_from_log(latest_log)
        if not run_id:
            raise RuntimeError(f"Missing run_id for {spec.key}")

        consolidated = _consolidate_run_jsonl(quantbuild_root=qb_root, run_id=run_id)
        role_dir = _bundle_run(
            qmos_root=qmos_root,
            qb_root=qb_root,
            experiment_id=args.experiment_id,
            role=spec.key.lower(),
            run_id=run_id,
            config_path=variant_path,
        )
        analytics_dir = role_dir / "analytics"
        analytics_dir.mkdir(parents=True, exist_ok=True)

        _run_guard_attribution(
            analytics_root=Path(_require_env("QUANTANALYTICS_ROOT")),
            runner_python=sys.executable,
            jsonl_path=consolidated,
            run_id=run_id,
            out_dir=analytics_dir,
        )

        prom = _run_promotion_gate(
            qmos_root=qmos_root,
            analytics_dir=analytics_dir,
            baseline_analytics_dir=baseline_analytics,
            max_dd_worsen_ratio=float(args.max_dd_worsen_ratio),
        )

        throughput = _read_json(analytics_dir / "throughput.json")
        max_dd = _max_drawdown_r_from_stability_path(analytics_dir / "edge_stability.json")

        rows.append(
            {
                "experiment": spec.key,
                "title": spec.title,
                "run_id": run_id,
                "role_dir": str(role_dir),
                "throughput": throughput,
                "promotion": prom,
                "max_drawdown_r": max_dd,
            }
        )

        if spec.key in ("A0_BASELINE", "B0_BASELINE"):
            baseline_analytics = analytics_dir

    gen_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary_path = qmos_root / "runs" / args.experiment_id / "THROUGHPUT_DISCOVERY_SUMMARY.md"
    summary_path.write_text(
        render_summary_md(
            generated_at_utc=gen_utc,
            experiment_id=args.experiment_id,
            base_config=base_config_abs,
            start_date=args.start_date,
            end_date=args.end_date,
            rows=rows,
            report_heading=report_heading,
        ),
        encoding="utf-8",
    )

    # Also write machine-readable registry beside the summary.
    registry_path = qmos_root / "runs" / args.experiment_id / "throughput_discovery_registry.json"
    registry_path.write_text(json.dumps({"generated_at_utc": gen_utc, "rows": rows}, indent=2), encoding="utf-8")

    compare_script = qmos_root / "scripts" / "throughput_discovery_compare.py"
    if not compare_script.is_file():
        raise RuntimeError(f"Missing compare script: {compare_script}")
    compare_cmd = [
        sys.executable,
        str(compare_script),
        "--experiment-root",
        str(qmos_root / "runs" / args.experiment_id),
        "--experiment-id",
        args.experiment_id,
        "--baseline-folder",
        compare_baseline_folder,
        "--max-dd-worsen-ratio",
        str(float(args.max_dd_worsen_ratio)),
    ]
    _run(compare_cmd, cwd=qmos_root, env=os.environ.copy())

    if args.update_research_ledger:
        _quantresearch_post_matrix_success(
            experiment_id=args.experiment_id,
            qr_root=qr_root,
            quantos_run_dir=qmos_root / "runs" / args.experiment_id,
        )

    print(str(summary_path))
    print(str(registry_path))
    print(str((qmos_root / "runs" / args.experiment_id / "THROUGHPUT_COMPARE.json").resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
