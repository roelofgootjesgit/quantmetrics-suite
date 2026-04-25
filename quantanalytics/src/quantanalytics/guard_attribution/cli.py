from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .attribution import analyze_guards
from .decision_cycles import reconstruct_decision_cycles
from .loader import load_events
from .report import generate_edge_report
from .scoring import score_decision_cycles
from .stability import analyze_stability
from .throughput import analyze_throughput
from .verdict import create_edge_verdict


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            row_copy = dict(row)
            if isinstance(row_copy.get("warnings"), list):
                row_copy["warnings"] = "|".join(row_copy["warnings"])
            writer.writerow(row_copy)


def _collect_warnings(loader_meta: dict, cycle_meta: dict, decision_quality: list[dict]) -> list[dict]:
    warnings = list(loader_meta.get("warnings", []))
    warning_counts = cycle_meta.get("warning_counts", {})
    for code, count in warning_counts.items():
        warnings.append({"code": code, "count": count})

    unknown_quality = sum(1 for row in decision_quality if row.get("quality_label") == "UNKNOWN")
    if unknown_quality:
        warnings.append({"code": "UNKNOWN_DECISION_QUALITY", "count": unknown_quality})
    return warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guard Attribution Engine")
    parser.add_argument("--events", required=True, help="Input JSONL file path")
    parser.add_argument("--run-id", default=None, help="Run ID override")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--copy-to-output-rapport", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    events = load_events(args.events)
    loader_meta = getattr(load_events, "last_metadata", {})
    cycles = reconstruct_decision_cycles(events)
    cycle_meta = getattr(reconstruct_decision_cycles, "last_metadata", {})
    guard_data = analyze_guards(cycles)
    quality_rows = score_decision_cycles(cycles)
    stability_data = analyze_stability(cycles)
    throughput_data = analyze_throughput(events, cycles)
    warnings = _collect_warnings(loader_meta, cycle_meta, quality_rows)
    verdict = create_edge_verdict(guard_data, stability_data, quality_rows, warnings)
    if args.run_id:
        verdict["run_id"] = args.run_id

    run_id = verdict.get("run_id")
    report_path = output_dir / "EDGE_REPORT.md"
    generate_edge_report(
        run_id=run_id,
        source_events=args.events,
        events_count=len(events),
        cycles=cycles,
        guard_attribution=guard_data,
        stability=stability_data,
        decision_quality=quality_rows,
        warnings=warnings,
        edge_verdict=verdict,
        throughput=throughput_data,
        output_path=str(report_path),
    )

    _write_json(output_dir / "guard_attribution.json", guard_data)
    _write_csv(output_dir / "decision_quality.csv", quality_rows)
    _write_json(output_dir / "edge_stability.json", stability_data)
    _write_json(output_dir / "edge_verdict.json", verdict)
    _write_json(output_dir / "warnings.json", warnings)
    _write_json(output_dir / "throughput.json", throughput_data)

    if args.copy_to_output_rapport:
        report_dir = Path(__file__).resolve().parents[3] / "output_rapport"
        report_dir.mkdir(parents=True, exist_ok=True)
        _write_json(report_dir / "guard_attribution.json", guard_data)
        _write_csv(report_dir / "decision_quality.csv", quality_rows)
        _write_json(report_dir / "edge_stability.json", stability_data)
        _write_json(report_dir / "edge_verdict.json", verdict)
        _write_json(report_dir / "warnings.json", warnings)
        _write_json(report_dir / "throughput.json", throughput_data)
        (report_dir / "EDGE_REPORT.md").write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

