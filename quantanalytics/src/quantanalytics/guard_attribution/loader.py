from __future__ import annotations

import json
from pathlib import Path

CORE_FIELDS = ["event_type", "timestamp_utc", "run_id", "decision_cycle_id", "payload"]


def load_events(path: str) -> list[dict]:
    source = Path(path)
    if source.suffix.lower() != ".jsonl":
        raise ValueError(f"Unsupported file type: {source.suffix}. Expected .jsonl")
    if not source.exists():
        raise FileNotFoundError(path)

    events: list[dict] = []
    event_types: dict[str, int] = {}
    missing_field_counts: dict[str, int] = {name: 0 for name in CORE_FIELDS}

    with source.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number}: {exc.msg}") from exc

            for field in CORE_FIELDS:
                if field not in event or event[field] in (None, ""):
                    missing_field_counts[field] += 1

            event_type = str(event.get("event_type", "UNKNOWN"))
            event_types[event_type] = event_types.get(event_type, 0) + 1
            events.append(event)

    warnings = []
    for field_name, count in missing_field_counts.items():
        if count > 0:
            warnings.append(
                {
                    "code": "MISSING_CORE_FIELD",
                    "field": field_name,
                    "count": count,
                }
            )

    metadata = {
        "source_path": str(source),
        "event_type_counts": event_types,
        "warnings": warnings,
        "total_events": len(events),
    }
    setattr(load_events, "last_metadata", metadata)
    return events

