"""CLI: load QuantLog JSONL and print analytics sections (read-only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quantmetrics_analytics.analysis.event_summary import format_event_summary
from quantmetrics_analytics.analysis.no_trade_analysis import format_no_trade_analysis
from quantmetrics_analytics.analysis.performance_summary import format_performance_summary
from quantmetrics_analytics.analysis.regime_performance import format_regime_performance
from quantmetrics_analytics.analysis.signal_funnel import format_signal_funnel
from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths
from quantmetrics_analytics.processing.normalize import events_to_dataframe

_VALID_REPORTS = frozenset({"summary", "no-trade", "funnel", "performance", "regime"})


def _parse_reports(spec: str) -> list[str]:
    s = spec.strip().lower()
    if s == "all":
        return ["summary", "no-trade", "funnel", "performance", "regime"]
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


def run(stdout=sys.stdout, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="QuantMetrics Analytics: QuantLog JSONL to stdout reports (read-only).",
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
        help="Directory: include all *.jsonl recursively",
    )
    parser.add_argument(
        "--reports",
        default="all",
        metavar="LIST",
        help=(
            "Comma-separated sections or 'all'. "
            "Choices: summary, no-trade, funnel, performance, regime."
        ),
    )
    args = parser.parse_args(argv)

    inputs = sum(
        1 for k in ("jsonl", "glob_pattern", "dir") if getattr(args, k, None) is not None
    )
    if inputs != 1:
        parser.error("Specify exactly one of: --jsonl, --glob, --dir")

    try:
        reports = _parse_reports(args.reports)
    except ValueError as exc:
        parser.error(str(exc))

    paths = _collect_paths(args)
    if not paths:
        print("No JSONL files found (check path / glob / directory).", file=sys.stderr)
        return 2

    events = load_events_from_paths(paths)
    df = events_to_dataframe(events)

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

    print("\n".join(blocks), file=stdout, end="")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
