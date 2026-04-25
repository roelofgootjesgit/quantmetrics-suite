#!/usr/bin/env python3
"""Wrapper: ``python scripts/validate_experiment.py --experiment-id EXP-...`` (from quantresearch repo root)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quantresearch.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["validate", *sys.argv[1:]]))
