"""QuantLog-compatible event emitter for QuantBuild runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


@dataclass
class QuantLogEmitter:
    base_path: Path
    source_component: str
    environment: str
    run_id: str
    session_id: str
    source_system: str = "quantbuild"
    source_seq: int = field(default=0, init=False)

    def _target_file(self, timestamp_utc: str) -> Path:
        day = timestamp_utc.split("T", maxsplit=1)[0]
        day_dir = self.base_path / day
        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir / f"{self.source_system}.jsonl"

    def emit(
        self,
        *,
        event_type: str,
        trace_id: str,
        payload: dict[str, Any],
        severity: str = "info",
        event_version: int = 1,
        timestamp_utc: str | None = None,
        order_ref: str | None = None,
        position_id: str | None = None,
        account_id: str | None = None,
        strategy_id: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        self.source_seq += 1
        ts = timestamp_utc or _utc_now_iso()
        event: dict[str, Any] = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "event_version": event_version,
            "timestamp_utc": ts,
            "ingested_at_utc": _utc_now_iso(),
            "source_system": self.source_system,
            "source_component": self.source_component,
            "environment": self.environment,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "source_seq": self.source_seq,
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

        target = self._target_file(ts)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True))
            handle.write("\n")
        return event

