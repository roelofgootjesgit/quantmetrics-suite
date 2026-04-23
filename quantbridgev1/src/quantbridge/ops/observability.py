from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class JsonlEventSink:
    path: str | Path
    source: str = "quantbridge"
    source_component: str = "observability"
    environment: str = "paper"
    run_id: str = ""
    session_id: str = ""
    _source_seq: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if not self.run_id:
            self.run_id = _utc_now_iso().replace(":", "").replace("-", "")
        if not self.session_id:
            self.session_id = f"{self.run_id}-session"

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._source_seq += 1
        timestamp_utc = _utc_now_iso().replace("+00:00", "Z")
        trace_id = str(payload.get("trace_id") or f"trace_qbr_{uuid4().hex[:12]}")
        order_ref = payload.get("order_ref")
        position_id = payload.get("position_id")
        account_id = payload.get("account_id")
        strategy_id = payload.get("strategy_id")
        symbol = payload.get("symbol") or payload.get("instrument")
        severity = str(payload.get("severity", "info"))
        event = {
            "event_id": str(uuid4()),
            "event_type": event_type,
            "event_version": 1,
            "timestamp_utc": timestamp_utc,
            "ingested_at_utc": _utc_now_iso().replace("+00:00", "Z"),
            "source_system": self.source,
            "source_component": self.source_component,
            "environment": self.environment,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "source_seq": self._source_seq,
            "trace_id": trace_id,
            "severity": severity,
            "payload": payload,
            # legacy fields retained for compatibility with existing scripts
            "ts": timestamp_utc,
            "source": self.source,
        }
        if isinstance(order_ref, str) and order_ref.strip():
            event["order_ref"] = order_ref
        trade_id = payload.get("trade_id")
        if isinstance(trade_id, str) and trade_id.strip():
            event["trade_id"] = trade_id
        decision_cycle_id = payload.get("decision_cycle_id")
        if isinstance(decision_cycle_id, str) and decision_cycle_id.strip():
            event["decision_cycle_id"] = decision_cycle_id.strip()
        if isinstance(position_id, str) and position_id.strip():
            event["position_id"] = position_id
        if isinstance(account_id, str) and account_id.strip():
            event["account_id"] = account_id
        if isinstance(strategy_id, str) and strategy_id.strip():
            event["strategy_id"] = strategy_id
        if isinstance(symbol, str) and symbol.strip():
            event["symbol"] = symbol
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")


@dataclass(frozen=True)
class EventSummary:
    total_events: int
    event_types: dict[str, int] = field(default_factory=dict)
    accounts: dict[str, int] = field(default_factory=dict)
    errors: int = 0
    window_minutes: int | None = None


def _parse_iso_ts(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    except Exception:
        return None


def summarize_jsonl_events(path: str | Path, since_minutes: int | None = None) -> EventSummary:
    event_counter: Counter[str] = Counter()
    account_counter: Counter[str] = Counter()
    errors = 0
    total = 0
    p = Path(path)
    if not p.exists():
        return EventSummary(total_events=0)

    cutoff: datetime | None = None
    if since_minutes is not None and int(since_minutes) > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=int(since_minutes))

    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            errors += 1
            continue
        event_dt = _parse_iso_ts(str(event.get("ts", "")))
        if cutoff is not None:
            if event_dt is None:
                continue
            if event_dt.tzinfo is None:
                event_dt = event_dt.replace(tzinfo=timezone.utc)
            if event_dt < cutoff:
                continue
        total += 1
        event_type = str(event.get("event_type", "unknown"))
        event_counter[event_type] += 1
        payload = event.get("payload", {}) or {}
        account_id = str(payload.get("account_id", "")).strip()
        if account_id:
            account_counter[account_id] += 1
        if "error" in event_type or payload.get("error"):
            errors += 1

    return EventSummary(
        total_events=total,
        event_types=dict(event_counter),
        accounts=dict(account_counter),
        errors=errors,
        window_minutes=since_minutes,
    )


def rotate_jsonl_events(path: str | Path, archive_dir: str | Path = "logs/archive") -> dict:
    src = Path(path)
    archive_root = Path(archive_dir)
    if not src.exists() or src.stat().st_size == 0:
        return {"rotated": False, "reason": "missing_or_empty", "source": str(src)}

    archive_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = archive_root / f"{src.stem}-{stamp}{src.suffix}"
    src.replace(dst)
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("", encoding="utf-8")
    return {
        "rotated": True,
        "source": str(src),
        "archive": str(dst),
    }

