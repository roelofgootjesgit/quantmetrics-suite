#!/usr/bin/env python3
"""Print a one-screen validation summary for a QuantLog day directory (or .jsonl file).

Uses ``validate_path`` from the library; exit code 1 if any errors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from quantlog.validate.validator import aggregate_validation_issue_codes, validate_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate QuantLog JSONL under a path and print a short report."
    )
    parser.add_argument("path", type=Path, help="Directory (day) or single .jsonl file")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text",
    )
    args = parser.parse_args()

    report = validate_path(args.path.expanduser())
    errors = [i for i in report.issues if i.level == "error"]
    warns = [i for i in report.issues if i.level == "warn"]

    if args.json:
        import json

        out = {
            "files_scanned": report.files_scanned,
            "lines_scanned": report.lines_scanned,
            "events_valid": report.events_valid,
            "errors_total": len(errors),
            "warnings_total": len(warns),
            "errors_by_code": aggregate_validation_issue_codes(errors),
            "warnings_by_code": aggregate_validation_issue_codes(warns),
        }
        print(json.dumps(out, indent=2, ensure_ascii=True))
    else:
        print(f"path={args.path}")
        print(f"files_scanned={report.files_scanned} lines_scanned={report.lines_scanned}")
        print(f"events_valid={report.events_valid}")
        print(f"errors={len(errors)} warnings={len(warns)}")
        if errors:
            print("errors_by_code:", aggregate_validation_issue_codes(errors))
        if warns:
            print("warnings_by_code:", aggregate_validation_issue_codes(warns))
        for issue in report.issues[:50]:
            print(f"  [{issue.level}] {issue.path}:{issue.line_number} {issue.message}")
        if len(report.issues) > 50:
            print(f"  ... and {len(report.issues) - 50} more issues")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
