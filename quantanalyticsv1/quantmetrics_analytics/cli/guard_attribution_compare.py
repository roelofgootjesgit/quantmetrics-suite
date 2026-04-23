"""CLI: Level B — baseline vs variant QuantLog run comparison (guard-off reruns)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from quantmetrics_analytics.cli.guard_attribution import _collect_paths
from quantmetrics_analytics.guard_attribution.compare_report_renderer import write_compare_reports
from quantmetrics_analytics.guard_attribution.rerun_compare import compare_guard_rerun_runs
from quantmetrics_analytics.ingestion.jsonl import load_events_from_paths


def run(argv: list[str] | None = None, *, stdout=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    parser = argparse.ArgumentParser(
        description="QuantMetrics — Guard attribution Level B (rerun causal compare)"
    )
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument("--variant-run-id", required=True)
    parser.add_argument("--baseline-label", default="baseline", help="Report label")
    parser.add_argument("--variant-label", default="variant", help="Report label")
    parser.add_argument("--guard-focus", default=None, help="Highlight one guard_name in summary")
    parser.add_argument("--jsonl", type=Path, default=None)
    parser.add_argument("--dir", type=Path, default=None)
    parser.add_argument("--glob-pattern", dest="glob_pattern", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)

    args = parser.parse_args(argv)

    paths = _collect_paths(args)
    if not paths:
        print("[guard-attribution-compare] No input JSONL paths resolved.", file=sys.stderr)
        return 2

    all_events = load_events_from_paths(paths)
    br = str(args.baseline_run_id).strip()
    vr = str(args.variant_run_id).strip()
    ev_b = [e for e in all_events if str(e.get("run_id", "")).strip() == br]
    ev_v = [e for e in all_events if str(e.get("run_id", "")).strip() == vr]

    if not ev_b:
        print(f"[guard-attribution-compare] No events for baseline run_id={br!r}", file=sys.stderr)
        return 3
    if not ev_v:
        print(f"[guard-attribution-compare] No events for variant run_id={vr!r}", file=sys.stderr)
        return 3

    gf = str(args.guard_focus).strip() if args.guard_focus else None
    if gf == "":
        gf = None

    payload = compare_guard_rerun_runs(
        ev_b,
        baseline_run_id=br,
        events_variant=ev_v,
        variant_run_id=vr,
        baseline_label=str(args.baseline_label),
        variant_label=str(args.variant_label),
        guard_focus=gf,
    )

    out_dir = args.output_dir
    if out_dir is None:
        env = os.environ.get("QUANTMETRICS_ANALYTICS_REPO_ROOT", "").strip()
        if env:
            base = Path(env).expanduser().resolve()
        else:
            base = Path.cwd().resolve()
        out_dir = base / "output_rapport"

    js_path, md_path = write_compare_reports(Path(out_dir), payload)
    print(f"[guard-attribution-compare] JSON: {js_path}", file=out)
    print(f"[guard-attribution-compare] MD:   {md_path}", file=out)
    print(json.dumps(payload.get("delta_trade_metrics", {}), indent=2), file=out)
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
