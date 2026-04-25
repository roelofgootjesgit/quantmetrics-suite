#!/usr/bin/env python3
"""Fail-fast checker for QuantMetrics suite path consistency."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.quantbuild.suite_layout import SuiteLayoutError, validate_suite_layout


def main() -> int:
    try:
        report = validate_suite_layout()
    except SuiteLayoutError as exc:
        print(f"Suite layout check failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
