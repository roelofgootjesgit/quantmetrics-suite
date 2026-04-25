from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for rel in ("quantbuild", "quantbuild/src", "quantlog/src", "quantanalytics/src"):
    candidate = ROOT / rel
    if candidate.is_dir():
        sys.path.insert(0, str(candidate))
