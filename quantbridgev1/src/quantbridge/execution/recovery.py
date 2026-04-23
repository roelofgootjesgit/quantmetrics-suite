from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from quantbridge.execution.broker_contract import BrokerContract
from quantbridge.execution.models import Position
from quantbridge.execution.state_validator import ReconcileActions, StateValidator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _position_to_registry_entry(position: Position, strategy: str) -> dict:
    return {
        "broker_id": position.trade_id,
        "entry": float(position.entry_price),
        "sl": float(position.sl) if position.sl is not None else None,
        "tp": float(position.tp) if position.tp is not None else None,
        "size": float(position.units),
        "direction": position.direction,
        "strategy": strategy,
        "current_price": float(position.current_price),
        "unrealized_pnl": float(position.unrealized_pnl),
        "open_time": position.open_time.isoformat() if position.open_time else None,
        "synced_at": _utc_now_iso(),
    }


@dataclass(frozen=True)
class RecoveryResult:
    connected: bool
    reconnect_attempts: int
    synced_positions: int
    rebuilt_symbols: List[str]
    dropped_symbols: List[str]
    updated_symbols: List[str]
    reconciliation: Dict[str, List[dict]]
    registry_path: str
    last_error: Optional[str] = None


class PositionRegistry:
    """Persist local position truth to disk."""

    def __init__(self, path: str | Path = "state/positions.json") -> None:
        self.path = Path(path)

    def load(self) -> Dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def save(self, data: Dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = json.dumps(data, indent=2, sort_keys=True)
        tmp_path.write_text(payload + "\n", encoding="utf-8")
        tmp_path.replace(self.path)

    def apply_reconciliation(
        self,
        broker_positions: List[Position],
        local_positions: Dict[str, dict],
        actions: ReconcileActions,
        strategy: str,
    ) -> Dict[str, dict]:
        # Broker is source of truth for open-position existence.
        local_map = {str(symbol).upper(): payload for symbol, payload in local_positions.items()}
        broker_map = {str(position.instrument).upper(): position for position in broker_positions}
        reconciled: Dict[str, dict] = {}

        for symbol, position in broker_map.items():
            local_entry = local_map.get(symbol, {})
            local_strategy = str(local_entry.get("strategy", "")).strip()
            reconciled[symbol] = _position_to_registry_entry(
                position=position,
                strategy=local_strategy or strategy,
            )

        # Keep actions referenced so future callers can use this method as an
        # explicit "apply(action-set)" step without changing persistence behavior.
        _ = actions
        self.save(reconciled)
        return reconciled


class ExecutionRecoveryManager:
    """Reconnect broker session and rebuild local state from broker truth."""

    def __init__(
        self,
        broker: BrokerContract,
        registry_path: str | Path = "state/positions.json",
        reconnect_retries: int = 3,
        reconnect_backoff_seconds: float = 2.0,
    ) -> None:
        self.broker = broker
        self.registry = PositionRegistry(registry_path)
        self.validator = StateValidator()
        self.reconnect_retries = max(1, int(reconnect_retries))
        self.reconnect_backoff_seconds = max(0.0, float(reconnect_backoff_seconds))

    def ensure_connected(self) -> tuple[bool, int, Optional[str]]:
        if self.broker.is_connected:
            return True, 0, None

        last_error: Optional[str] = None
        for attempt in range(1, self.reconnect_retries + 1):
            if self.broker.connect():
                return True, attempt, None
            health = self.broker.health_check()
            last_error = health.last_error or "connect_failed"
            if attempt < self.reconnect_retries:
                time.sleep(self.reconnect_backoff_seconds * attempt)

        return False, self.reconnect_retries, last_error

    def startup_recover(self, instrument: Optional[str] = None, strategy: str = "unknown") -> RecoveryResult:
        connected, attempts, last_error = self.ensure_connected()
        if not connected:
            return RecoveryResult(
                connected=False,
                reconnect_attempts=attempts,
                synced_positions=0,
                rebuilt_symbols=[],
                dropped_symbols=[],
                updated_symbols=[],
                reconciliation={"add": [], "remove": [], "update": []},
                registry_path=str(self.registry.path),
                last_error=last_error,
            )

        try:
            positions = self.broker.sync_positions(instrument=instrument)
        except Exception as exc:  # pragma: no cover
            return RecoveryResult(
                connected=True,
                reconnect_attempts=attempts,
                synced_positions=0,
                rebuilt_symbols=[],
                dropped_symbols=[],
                updated_symbols=[],
                reconciliation={"add": [], "remove": [], "update": []},
                registry_path=str(self.registry.path),
                last_error=f"sync_failed: {exc}",
            )

        local_positions = self.registry.load()
        actions = self.validator.reconcile(
            broker_positions=positions,
            local_positions=local_positions,
        )
        reconciled = self.registry.apply_reconciliation(
            broker_positions=positions,
            local_positions=local_positions,
            actions=actions,
            strategy=strategy,
        )
        rebuilt_symbols = sorted(reconciled.keys())
        dropped_symbols = sorted([item["symbol"] for item in actions.remove])
        updated_symbols = sorted([item["symbol"] for item in actions.update])
        return RecoveryResult(
            connected=True,
            reconnect_attempts=attempts,
            synced_positions=len(positions),
            rebuilt_symbols=rebuilt_symbols,
            dropped_symbols=dropped_symbols,
            updated_symbols=updated_symbols,
            reconciliation={
                "add": actions.add,
                "remove": actions.remove,
                "update": actions.update,
            },
            registry_path=str(self.registry.path),
            last_error=None,
        )
