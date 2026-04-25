#!/usr/bin/env python3
"""Write links.json: ``python scripts/link_artifacts.py --experiment-id EXP-... --quantos-run-dir ...``."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quantresearch.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["link-artifacts", *sys.argv[1:]]))
