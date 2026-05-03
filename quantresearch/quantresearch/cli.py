"""CLI for QuantResearch experiment ledger v1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quantresearch.dossier import write_experiment_dossier
from quantresearch.ledger import (
    link_artifacts,
    mark_experiment_completed,
    validate_experiment,
    write_research_ledger_md,
)


def _cmd_validate(args: argparse.Namespace) -> int:
    mode = getattr(args, "mode", "full") or "full"
    errs = validate_experiment(args.experiment_id, mode=mode)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print(f"OK: experiment {args.experiment_id} passes ledger validation ({mode})")
    return 0


def _cmd_summarize(args: argparse.Namespace) -> int:
    out = write_research_ledger_md()
    print(str(out))
    return 0


def _cmd_link_artifacts(args: argparse.Namespace) -> int:
    p = Path(args.quantos_run_dir).expanduser()
    out = link_artifacts(args.experiment_id, quantos_run_dir=p)
    print(str(out))
    return 0


def _cmd_dossier(args: argparse.Namespace) -> int:
    out = write_experiment_dossier(args.experiment_id)
    print(str(out))
    return 0


def _cmd_hyp002_pipeline(args: argparse.Namespace) -> int:
    from quantresearch.hyp002_research_pipeline import main as hyp002_main

    argv: list[str] = []
    if str(getattr(args, "manifest", "") or "").strip():
        argv.extend(["--manifest", str(args.manifest).strip()])
    if args.dry_run:
        argv.append("--dry-run")
    if args.no_registry:
        argv.append("--no-registry")
    return hyp002_main(argv)


def _cmd_mark_completed(args: argparse.Namespace) -> int:
    ts = str(getattr(args, "completed_at_utc", "") or "").strip()
    mark_experiment_completed(args.experiment_id, completed_at_utc=ts or None)
    print(f"OK: experiment {args.experiment_id} marked completed in experiment.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(prog="quantresearch.cli", description="QuantResearch experiment ledger")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate experiment folder + ledger rules")
    p_val.add_argument("--experiment-id", required=True)
    p_val.add_argument(
        "--mode",
        choices=("full", "pre_run"),
        default="full",
        help="pre_run = QuantOS matrix gate (hypothesis + plan + planned/running only); full = audit",
    )
    p_val.set_defaults(func=_cmd_validate)

    p_sum = sub.add_parser("summarize", help="Regenerate RESEARCH_LEDGER.md from experiment folders")
    p_sum.set_defaults(func=_cmd_summarize)

    p_dossier = sub.add_parser(
        "dossier",
        help="Write EXPERIMENT_DOSSIER.md (read-only bundle of hypothesis, plan, links, compare, verdicts, decision)",
    )
    p_dossier.add_argument("--experiment-id", required=True)
    p_dossier.set_defaults(func=_cmd_dossier)

    p_link = sub.add_parser("link-artifacts", help="Write links.json pointing at a QuantOS run directory")
    p_link.add_argument("--experiment-id", required=True)
    p_link.add_argument(
        "--quantos-run-dir",
        required=True,
        help="Path to quantmetrics_os/runs/<experiment_id>/ (absolute or under suite root)",
    )
    p_link.set_defaults(func=_cmd_link_artifacts)

    p_h2 = sub.add_parser(
        "hyp002-pipeline",
        help="Run HYP-002 QuantBuild bundle (V5A+expansion-block), write quantresearch/runs/…/metrics_bundle.json, upsert EXP-002",
    )
    p_h2.add_argument(
        "--manifest",
        type=str,
        default="",
        help="Path to pipelines/hyp002_promotion_bundle.json (default: package default)",
    )
    p_h2.add_argument("--dry-run", action="store_true")
    p_h2.add_argument("--no-registry", action="store_true")
    p_h2.set_defaults(func=_cmd_hyp002_pipeline)

    p_done = sub.add_parser(
        "mark-completed",
        help="Set experiment.json status to completed and completed_at_utc (after artifacts are linked)",
    )
    p_done.add_argument("--experiment-id", required=True)
    p_done.add_argument(
        "--completed-at-utc",
        default="",
        help="ISO-8601 UTC timestamp (default: now)",
    )
    p_done.set_defaults(func=_cmd_mark_completed)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
