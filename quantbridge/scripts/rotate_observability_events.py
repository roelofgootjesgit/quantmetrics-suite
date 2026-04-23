from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbridge.ops.observability import rotate_jsonl_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate QuantBridge JSONL observability log file.")
    parser.add_argument("--events-file", default="logs/events.jsonl")
    parser.add_argument("--archive-dir", default="logs/archive")
    args = parser.parse_args()

    result = rotate_jsonl_events(path=args.events_file, archive_dir=args.archive_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
