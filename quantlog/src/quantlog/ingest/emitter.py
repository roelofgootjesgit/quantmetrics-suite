"""Event emitter utilities for QuantLog JSONL storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class EventEmitter:
    base_path: Path
    source_system: str
    source_component: str
    environment: str
    run_id: str
    session_id: str
    _source_seq_counter: int = 0

    def _target_file(self, timestamp_utc: str) -> Path:
        day = timestamp_utc.split("T", maxsplit=1)[0]
        target_dir = self.base_path / day
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"{self.source_system}.jsonl"

    def emit_event(
        self,
        *,
        event_type: str,
        trace_id: str,
        payload: dict[str, Any],
        event_version: int = 1,
        severity: str = "info",
        order_ref: str | None = None,
        position_id: str | None = None,
        account_id: str | None = None,
        strategy_id: str | None = None,
        symbol: str | None = None,
        timestamp_utc: str | None = None,
        source_seq: int | None = None,
        decision_cycle_id: str | None = None,
    ) -> dict[str, Any]:
        ts = timestamp_utc or utc_now_iso()
        ingested_at = utc_now_iso()
        if source_seq is None:
            self._source_seq_counter += 1
            seq = self._source_seq_counter
        else:
            seq = source_seq
            if source_seq > self._source_seq_counter:
                self._source_seq_counter = source_seq
        event: dict[str, Any] = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "event_version": event_version,
            "timestamp_utc": ts,
            "ingested_at_utc": ingested_at,
            "source_system": self.source_system,
            "source_component": self.source_component,
            "environment": self.environment,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "source_seq": seq,
            "trace_id": trace_id,
            "severity": severity,
            "payload": payload,
        }
        if order_ref:
            event["order_ref"] = order_ref
        if position_id:
            event["position_id"] = position_id
        if account_id:
            event["account_id"] = account_id
        if strategy_id:
            event["strategy_id"] = strategy_id
        if symbol:
            event["symbol"] = symbol
        if decision_cycle_id:
            event["decision_cycle_id"] = decision_cycle_id

        target = self._target_file(ts)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True))
            handle.write("\n")
        return event

