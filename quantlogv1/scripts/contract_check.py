"""Contract check for QuantBuild/QuantBridge fixture logs."""

from __future__ import annotations

import argparse
from pathlib import Path

from quantlog.validate.validator import validate_path


def _run_check(path: Path, max_warnings: int) -> tuple[bool, int, int]:
    report = validate_path(path)
    errors = sum(1 for issue in report.issues if issue.level == "error")
    warnings = sum(1 for issue in report.issues if issue.level == "warn")
    ok = errors == 0 and warnings <= max_warnings
    return ok, errors, warnings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate contract fixture logs")
    parser.add_argument(
        "--contracts-path",
        default="tests/fixtures/contracts",
        help="Path containing contract fixture jsonl files",
    )
    parser.add_argument(
        "--max-warnings",
        type=int,
        default=0,
        help="Maximum allowed warnings",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.contracts_path)
    qb_path = root / "quantbuild_dry_run.jsonl"
    qbr_path = root / "quantbridge_dry_run.jsonl"

    ok_qb, qb_errors, qb_warnings = _run_check(qb_path, args.max_warnings)
    ok_qbr, qbr_errors, qbr_warnings = _run_check(qbr_path, args.max_warnings)

    print("CONTRACT CHECK RESULTS")
    print(f"quantbuild: errors={qb_errors} warnings={qb_warnings} ok={ok_qb}")
    print(f"quantbridge: errors={qbr_errors} warnings={qbr_warnings} ok={ok_qbr}")

    if not (ok_qb and ok_qbr):
        print("[FAIL] Contract check failed")
        return 1
    print("[PASS] Contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

