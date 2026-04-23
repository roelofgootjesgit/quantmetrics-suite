"""CLI: Guard Attribution MVP from QuantLog JSONL."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from quantmetrics_analytics.guard_attribution.pipeline import run_guard_attribution
from quantmetrics_analytics.guard_attribution.report_renderer import write_reports
from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths


def _collect_paths(args: argparse.Namespace) -> list[Path]:
    if getattr(args, "jsonl", None):
        p = args.jsonl.expanduser().resolve()
        return [p] if p.is_file() else []
    if getattr(args, "glob_pattern", None):
        from glob import glob as glob_fn

        paths = sorted(Path(p).expanduser().resolve() for p in glob_fn(args.glob_pattern))
        return [p for p in paths if p.is_file()]
    if getattr(args, "dir", None):
        d = args.dir.expanduser().resolve()
        if not d.is_dir():
            return []
        return sorted({p for p in d.rglob("*.jsonl") if p.is_file()})
    return []


def run(argv: list[str] | None = None, *, stdout=None) -> int:
    """Run CLI; ``stdout`` defaults to ``sys.stdout`` (capturable in tests)."""
    out = stdout if stdout is not None else sys.stdout
    parser = argparse.ArgumentParser(description="QuantMetrics — Guard Attribution MVP")
    parser.add_argument("--run-id", required=True, help="Envelope run_id (exact match)")
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=None,
        help="Single QuantLog JSONL file",
    )
    parser.add_argument("--dir", type=Path, default=None, help="Walk directory for *.jsonl")
    parser.add_argument("--glob-pattern", dest="glob_pattern", default=None, help="Glob for *.jsonl")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write guard_attribution_<run_id>.* (default: output_rapport cwd / repo)",
    )
    parser.add_argument(
        "--min-slice-n",
        type=int,
        default=5,
        help="Minimum executed trades in a slice before trusting slice mean (below: fallback)",
    )

    args = parser.parse_args(argv)

    paths = _collect_paths(args)
    if not paths:
        print("[guard-attribution] No input JSONL paths resolved.", file=sys.stderr)
        return 2

    events = load_events_from_paths(paths)
    rid = str(args.run_id).strip()
    events = [e for e in events if str(e.get("run_id", "")).strip() == rid]

    if not events:
        print(f"[guard-attribution] No events after run_id filter={rid!r}", file=sys.stderr)
        return 3

    payload = run_guard_attribution(events, run_id=rid, min_slice_n=int(args.min_slice_n))

    out_dir = args.output_dir
    if out_dir is None:
        env = os.environ.get("QUANTMETRICS_ANALYTICS_REPO_ROOT", "").strip()
        if env:
            base = Path(env).expanduser().resolve()
        else:
            base = Path.cwd().resolve()
        out_dir = base / "output_rapport"

    js_path, md_path = write_reports(Path(out_dir), rid, payload)
    print(f"[guard-attribution] JSON: {js_path}", file=out)
    print(f"[guard-attribution] MD:   {md_path}", file=out)
    print(json.dumps(payload.get("guard_score_table", []), indent=2), file=out)
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
