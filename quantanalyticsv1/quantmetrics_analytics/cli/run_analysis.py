"""CLI: load QuantLog JSONL and print analytics sections (read-only)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from quantmetrics_analytics.analysis.event_summary import format_event_summary
from quantmetrics_analytics.analysis.no_trade_analysis import format_no_trade_analysis
from quantmetrics_analytics.analysis.performance_summary import format_performance_summary
from quantmetrics_analytics.analysis.regime_performance import format_regime_performance
from quantmetrics_analytics.analysis.signal_funnel import format_signal_funnel
from quantmetrics_analytics.analysis.extended_diagnostics import format_extended_report_text
from quantmetrics_analytics.analysis.priority_insights import format_key_findings_markdown
from quantmetrics_analytics.analysis.run_summary import build_run_summary, run_summary_to_markdown
from quantmetrics_analytics.datasets.closed_trades import trade_closed_events_to_df
from quantmetrics_analytics.datasets.decisions import trade_actions_to_decisions_df
from quantmetrics_analytics.datasets.executions import execution_events_to_df
from quantmetrics_analytics.datasets.guard_decisions import risk_guard_events_to_df
from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths
from quantmetrics_analytics.processing.normalize import events_to_dataframe

_VALID_REPORTS = frozenset({"summary", "no-trade", "funnel", "performance", "regime", "research"})


def _parse_reports(spec: str) -> list[str]:
    s = spec.strip().lower()
    if s == "all":
        return ["summary", "no-trade", "funnel", "performance", "regime", "research"]
    parts = [p.strip().lower() for p in spec.split(",") if p.strip()]
    bad = [p for p in parts if p not in _VALID_REPORTS]
    if bad:
        raise ValueError(f"Unknown report(s): {bad}. Valid: {sorted(_VALID_REPORTS)} or all")
    return parts


def _collect_paths(args: argparse.Namespace) -> list[Path]:
    if getattr(args, "jsonl", None):
        p = args.jsonl.expanduser().resolve()
        return [p] if p.is_file() else []
    if getattr(args, "glob_pattern", None):
        from glob import glob

        paths = sorted(Path(p).expanduser().resolve() for p in glob(args.glob_pattern))
        return [p for p in paths if p.is_file()]
    if getattr(args, "dir", None):
        d = args.dir.expanduser().resolve()
        if not d.is_dir():
            return []
        return sorted({p for p in d.rglob("*.jsonl") if p.is_file()})
    return []


def discover_quantbuild_quantlog_dir() -> Path | None:
    """Canonical folder for QuantBuild QuantLog JSONL (`data/quantlog_events`).

    Matches QuantBuild defaults (``configs/default.yaml``: ``quantlog.base_path``).
    Resolution order:

    1. Env ``QUANTMETRICS_QUANTLOG_DIR`` (must exist).
    2. Current repo if cwd is inside a QuantBuild checkout: ``<quantbuild-root>/data/quantlog_events``.
    3. Multi-root workspace: sibling ``quantbuildv1/data/quantlog_events`` (shallow scan).

    Returns ``None`` when nothing matches.
    """
    env = os.environ.get("QUANTMETRICS_QUANTLOG_DIR", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        return p if p.is_dir() else None

    cwd = Path.cwd().resolve()

    # Inside QuantBuild checkout (any folder under repo root).
    scan_roots = [cwd, *list(cwd.parents)[:24]]
    for d in scan_roots:
        marker = d / "src" / "quantbuild"
        ql = d / "data" / "quantlog_events"
        if marker.is_dir() and ql.is_dir():
            return ql

    shallow = [cwd, *list(cwd.parents)[:6]]
    for d in shallow:
        qb = d / "quantbuildv1"
        ql = qb / "data" / "quantlog_events"
        if ql.is_dir():
            return ql

    return None


def _inject_default_quantlog_dir_if_needed(args: argparse.Namespace) -> Path | None:
    """If user gave no input flags, default to QuantBuild quantlog folder when found."""
    if any(getattr(args, k, None) for k in ("jsonl", "glob_pattern", "dir")):
        return None
    found = discover_quantbuild_quantlog_dir()
    if found is not None:
        args.dir = found
        return found
    return None


def _repo_root() -> Path:
    """Directory used as base for ``output_rapport/`` when no env override.

    With ``pip install`` (wheel), ``__file__`` lives under ``site-packages``; resolving
    ``parents[2]`` then points at ``site-packages``, so reports would land in a hidden
    folder users never open. Prefer: explicit env, walk up from :func:`os.getcwd`, then
    fall back to cwd so ``./output_rapport`` matches the shell location.
    """
    env = os.environ.get("QUANTMETRICS_ANALYTICS_REPO_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()

    here = Path(__file__).resolve()
    if any(p.lower() == "site-packages" for p in here.parts):
        cwd = Path.cwd().resolve()
        for d in [cwd, *cwd.parents]:
            pkg = d / "quantmetrics_analytics"
            meta = d / "pyproject.toml"
            if pkg.is_dir() and meta.is_file():
                try:
                    txt = meta.read_text(encoding="utf-8")
                except OSError:
                    continue
                if "quantmetrics-analytics" in txt:
                    return d
        return cwd

    # Editable checkout: .../quantanalyticsv1/quantmetrics_analytics/cli/run_analysis.py
    return here.parents[2]


def _is_quantanalytics_clone_root(d: Path) -> bool:
    """True if ``d`` looks like the quantanalytics repo (package + pyproject)."""
    meta = d / "pyproject.toml"
    pkg = d / "quantmetrics_analytics"
    if not (meta.is_file() and pkg.is_dir()):
        return False
    try:
        return "quantmetrics-analytics" in meta.read_text(encoding="utf-8")
    except OSError:
        return False


def _output_rapport_dir() -> Path:
    """Directory where default ``*.txt`` reports are written (created on write).

    Priority: env ``QUANTMETRICS_ANALYTICS_OUTPUT_DIR``, then resolve the
    ``quantanalyticsv1`` checkout from :func:`os.getcwd` (current or parent dirs,
    or sibling ``quantanalyticsv1/`` when using a multi-root workspace), then
    :func:`_repo_root` / ``output_rapport``. This keeps backtest/analytics runs
    landing in ``<clone>/output_rapport`` even when the shell cwd is elsewhere
    under the same workspace.
    """
    out = os.environ.get("QUANTMETRICS_ANALYTICS_OUTPUT_DIR", "").strip()
    if out:
        return Path(out).expanduser().resolve()

    cwd = Path.cwd().resolve()
    # Inside clone: .../quantanalyticsv1 (or renamed folder with same layout)
    for d in [cwd, *cwd.parents]:
        if _is_quantanalytics_clone_root(d):
            return d / "output_rapport"

    # Multi-root workspace: a parent folder contains sibling ``quantanalyticsv1/``.
    # Cap depth so deep temp dirs (e.g. pytest) do not walk up to the user's home
    # directory and steal the canonical clone there.
    shallow = [cwd, *list(cwd.parents)[:5]]
    for d in shallow:
        qa = d / "quantanalyticsv1"
        if _is_quantanalytics_clone_root(qa):
            return qa / "output_rapport"

    return _repo_root() / "output_rapport"


def _safe_filename_part(raw: str, *, max_len: int = 72) -> str:
    out = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw)
    out = out.strip("_")[:max_len].strip("_")
    return out or "report"


def _default_report_path(args: argparse.Namespace, paths: list[Path]) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
    out_dir = _output_rapport_dir()
    if getattr(args, "jsonl", None):
        stem = _safe_filename_part(paths[0].stem) if paths else "report"
        name = f"{stem}_{ts}.txt"
    elif getattr(args, "glob_pattern", None):
        name = f"glob_{len(paths)}_files_{ts}.txt"
    else:
        stem = _safe_filename_part(Path(args.dir).resolve().name)
        name = f"{stem}_{ts}.txt"
    return out_dir / name


def run(stdout=sys.stdout, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "QuantMetrics Analytics: QuantLog JSONL reports (read-only). "
            "By default writes UTF-8 text under output_rapport/ in this repo. "
            "Omit --jsonl/--glob/--dir to ingest QuantBuild backtest/live JSONL from "
            "the canonical data/quantlog_events folder when discoverable "
            "(QUANTMETRICS_QUANTLOG_DIR overrides)."
        ),
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        metavar="PATH",
        help="Single JSONL file",
    )
    parser.add_argument(
        "--glob",
        dest="glob_pattern",
        metavar="PATTERN",
        help='Glob pattern e.g. "logs/**/*.jsonl"',
    )
    parser.add_argument(
        "--dir",
        type=Path,
        metavar="DIR",
        help=(
            "Directory: include all *.jsonl recursively. "
            "If you omit --jsonl, --glob and --dir, the CLI tries QuantBuild's "
            "default ``data/quantlog_events`` (see discover_quantbuild_quantlog_dir)."
        ),
    )
    parser.add_argument(
        "--reports",
        default="all",
        metavar="LIST",
        help=(
            "Comma-separated sections or 'all'. "
            "Choices: summary, no-trade, funnel, performance, regime, research "
            "(research = ANALYTICS_OUTPUT_GAPS-style diagnostics)."
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        metavar="PATH",
        help=(
            "Write the report to this explicit path (UTF-8). "
            "Overrides the default output_rapport/ file. "
            "Confirmation is printed on stderr."
        ),
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the report to stdout instead of creating a file under output_rapport/.",
    )
    parser.add_argument(
        "--no-key-findings-md",
        action="store_true",
        help="Do not write *_KEY_FINDINGS.md next to the main report (default: write operator Markdown).",
    )
    parser.add_argument(
        "--run-id",
        dest="run_id",
        metavar="RUN_ID",
        help=(
            "Keep only events whose envelope ``run_id`` equals this string. "
            "Use after backtests when ``data/quantlog_events`` mixes many runs — "
            "otherwise context/funnel percentages reflect legacy rows, not the latest emitters."
        ),
    )
    parser.add_argument(
        "--export-decisions-tsv",
        type=Path,
        metavar="PATH",
        help="Also write QuantBuild trade_action rows as TSV (decisions grain MVP).",
    )
    parser.add_argument(
        "--export-guard-tsv",
        type=Path,
        metavar="PATH",
        help="Also write QuantBuild risk_guard_decision rows as TSV.",
    )
    parser.add_argument(
        "--export-executions-tsv",
        type=Path,
        metavar="PATH",
        help="Also write order_submitted / order_filled / trade_executed rows as TSV.",
    )
    parser.add_argument(
        "--export-closed-trades-tsv",
        type=Path,
        metavar="PATH",
        help="Also write trade_closed rows as TSV.",
    )
    parser.add_argument(
        "--run-summary-json",
        type=Path,
        metavar="PATH",
        help="Write structured run_summary.json (funnel, NO_ACTION, expectancy stub).",
    )
    parser.add_argument(
        "--run-summary-md",
        type=Path,
        metavar="PATH",
        help="Optional Markdown mirror of run summary (requires --run-summary-json data).",
    )
    args = parser.parse_args(argv)

    default_ql_dir = _inject_default_quantlog_dir_if_needed(args)

    inputs = sum(
        1 for k in ("jsonl", "glob_pattern", "dir") if getattr(args, k, None) is not None
    )
    if inputs != 1:
        parser.error(
            "Specify exactly one of: --jsonl, --glob, --dir "
            "(or omit all three to use the default QuantBuild QuantLog folder when discoverable; "
            "set QUANTMETRICS_QUANTLOG_DIR)."
        )

    try:
        reports = _parse_reports(args.reports)
    except ValueError as exc:
        parser.error(str(exc))

    if getattr(args, "stdout", False) and getattr(args, "output", None) is not None:
        parser.error("Choose either --stdout or --output/-o, not both.")

    if default_ql_dir is not None:
        print(
            f"Using default QuantLog input directory (QuantBuild): {default_ql_dir}",
            file=sys.stderr,
        )

    paths = _collect_paths(args)
    if not paths:
        hint = ""
        if default_ql_dir is not None:
            hint = f" (no *.jsonl under {default_ql_dir}; run a backtest with quantlog.enabled or copy JSONL here)"
        print(f"No JSONL files found (check path / glob / directory).{hint}", file=sys.stderr)
        return 2

    events = load_events_from_paths(paths)
    run_id_filter = getattr(args, "run_id", None)
    if run_id_filter is not None:
        run_id_filter = str(run_id_filter).strip()
    if not run_id_filter:
        run_id_filter = os.environ.get("QUANTMETRICS_ANALYTICS_RUN_ID", "").strip() or None
    if run_id_filter:
        n0 = len(events)
        events = [e for e in events if str(e.get("run_id", "")).strip() == run_id_filter]
        print(
            f"run_id filter {run_id_filter!r}: kept {len(events)}/{n0} events",
            file=sys.stderr,
        )
        if n0 > 0 and len(events) == 0:
            print(
                "error: no events matched --run-id / QUANTMETRICS_ANALYTICS_RUN_ID "
                "(typo or no matching JSONL under the selected inputs)",
                file=sys.stderr,
            )
            return 3
    df = events_to_dataframe(events)

    export_path = getattr(args, "export_decisions_tsv", None)
    if export_path is not None:
        dec = trade_actions_to_decisions_df(events)
        export_dest = export_path.expanduser().resolve()
        export_dest.parent.mkdir(parents=True, exist_ok=True)
        dec.to_csv(export_dest, sep="\t", index=False, encoding="utf-8")
        print(f"Decisions TSV written to: {export_dest}", file=sys.stderr)

    gp = getattr(args, "export_guard_tsv", None)
    if gp is not None:
        gdf = risk_guard_events_to_df(events)
        dest = gp.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_csv(dest, sep="\t", index=False, encoding="utf-8")
        print(f"Guard decisions TSV written to: {dest}", file=sys.stderr)

    ep = getattr(args, "export_executions_tsv", None)
    if ep is not None:
        edf = execution_events_to_df(events)
        dest = ep.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        edf.to_csv(dest, sep="\t", index=False, encoding="utf-8")
        print(f"Executions TSV written to: {dest}", file=sys.stderr)

    cp = getattr(args, "export_closed_trades_tsv", None)
    if cp is not None:
        cdf = trade_closed_events_to_df(events)
        dest = cp.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        cdf.to_csv(dest, sep="\t", index=False, encoding="utf-8")
        print(f"Closed trades TSV written to: {dest}", file=sys.stderr)

    run_summary: dict | None = None

    def _ensure_run_summary() -> dict:
        nonlocal run_summary
        if run_summary is None:
            run_summary = build_run_summary(events=events, df=df, input_paths=paths)
        return run_summary

    rs_json = getattr(args, "run_summary_json", None)
    if rs_json is not None:
        summ = _ensure_run_summary()
        dest = rs_json.expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(summ, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Run summary JSON written to: {dest}", file=sys.stderr)

    rs_md = getattr(args, "run_summary_md", None)
    if rs_md is not None:
        summ = _ensure_run_summary()
        md_dest = rs_md.expanduser().resolve()
        md_dest.parent.mkdir(parents=True, exist_ok=True)
        md_dest.write_text(run_summary_to_markdown(summ), encoding="utf-8")
        print(f"Run summary Markdown written to: {md_dest}", file=sys.stderr)

    blocks: list[str] = []
    for name in reports:
        if name == "summary":
            blocks.append(format_event_summary(df))
        elif name == "no-trade":
            blocks.append(format_no_trade_analysis(df))
        elif name == "funnel":
            blocks.append(format_signal_funnel(df))
        elif name == "performance":
            blocks.append(format_performance_summary(df))
        elif name == "regime":
            blocks.append(format_regime_performance(df))
        elif name == "research":
            summ = _ensure_run_summary()
            blocks.append(format_extended_report_text(summ))

    text = "\n".join(blocks)

    no_kf = getattr(args, "no_key_findings_md", False)

    if getattr(args, "stdout", False):
        print(text, file=stdout, end="")
        if not no_kf:
            summ = _ensure_run_summary()
            kf_dir = _output_rapport_dir()
            kf_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")
            kf_dest = kf_dir / f"stdout_run_{ts}_KEY_FINDINGS.md"
            kf_dest.write_text(format_key_findings_markdown(summ), encoding="utf-8")
            print(f"Key findings written to: {kf_dest}", file=sys.stderr)
        return 0

    dest: Path | None
    explicit = getattr(args, "output", None)
    if explicit is not None:
        dest = explicit.expanduser().resolve()
    else:
        dest = _default_report_path(args, paths).resolve()

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"Report written to: {dest}", file=sys.stderr)
    if not no_kf:
        summ = _ensure_run_summary()
        kf_dest = dest.parent / f"{dest.stem}_KEY_FINDINGS.md"
        kf_dest.write_text(format_key_findings_markdown(summ), encoding="utf-8")
        print(f"Key findings written to: {kf_dest}", file=sys.stderr)
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
