from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib import parse, request

from quantbridge.accounts.account_state_machine import AccountStateMachine
from quantbridge.execution.broker_contract import BrokerContract
from quantbridge.execution.recovery import PositionRegistry
from quantbridge.execution.state_validator import ReconcileActions, StateValidator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def send_telegram_alert(bot_token: str, chat_id: str, message: str) -> bool:
    if not bot_token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
        req = request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with request.urlopen(req, timeout=10) as response:
            return int(getattr(response, "status", 200)) == 200
    except Exception:
        return False


@dataclass(frozen=True)
class RuntimeStepResult:
    timestamp: str
    connected: bool
    reconnect_attempts: int
    synced_positions: int
    mismatch_count: int
    mismatch_streak: int
    failsafe_triggered: bool
    paused: bool
    reconciliation: dict
    last_error: Optional[str] = None


class RuntimeControlLoop:
    """Continuous runtime reconciliation and safety control."""

    def __init__(
        self,
        broker: BrokerContract,
        registry_path: str | Path = "state/positions.json",
        pause_file_path: str | Path = "state/trading.paused",
        poll_interval_seconds: float = 5.0,
        reconnect_retries: int = 3,
        reconnect_backoff_seconds: float = 2.0,
        mismatch_streak_failsafe: int = 3,
        close_on_failsafe: bool = True,
        account_id: str = "",
        account_state_machine: Optional[AccountStateMachine] = None,
        alert_callback: Optional[Callable[[str], None]] = None,
        event_callback: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.broker = broker
        self.registry = PositionRegistry(registry_path)
        self.pause_file_path = Path(pause_file_path)
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds))
        self.reconnect_retries = max(1, int(reconnect_retries))
        self.reconnect_backoff_seconds = max(0.0, float(reconnect_backoff_seconds))
        self.mismatch_streak_failsafe = max(1, int(mismatch_streak_failsafe))
        self.close_on_failsafe = bool(close_on_failsafe)
        self.account_id = str(account_id or "")
        self.account_state_machine = account_state_machine
        self.validator = StateValidator()
        self.alert_callback = alert_callback
        self.event_callback = event_callback
        self._mismatch_streak = 0
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def _alert(self, text: str) -> None:
        if self.alert_callback is None:
            return
        try:
            self.alert_callback(text)
        except Exception:
            pass

    def _emit_event(self, event_type: str, payload: dict) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(event_type, payload)
        except Exception:
            pass

    def _write_pause_marker(self, reason: str) -> None:
        self.pause_file_path.parent.mkdir(parents=True, exist_ok=True)
        marker = {
            "paused": True,
            "reason": reason,
            "created_at": _utc_now_iso(),
        }
        self.pause_file_path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")

    def _ensure_connected(self) -> tuple[bool, int, Optional[str]]:
        if self.broker.is_connected:
            return True, 0, None

        last_error: Optional[str] = None
        for attempt in range(1, self.reconnect_retries + 1):
            if self.broker.connect():
                self._alert(f"[runtime] reconnect success attempt={attempt}")
                return True, attempt, None
            health = self.broker.health_check()
            last_error = health.last_error or "connect_failed"
            if attempt < self.reconnect_retries:
                time.sleep(self.reconnect_backoff_seconds * attempt)

        self._alert(f"[runtime] reconnect failed after {self.reconnect_retries} attempts error={last_error}")
        return False, self.reconnect_retries, last_error

    def _close_all_positions(self, instrument: Optional[str] = None) -> int:
        closed = 0
        try:
            positions = self.broker.sync_positions(instrument=instrument)
        except Exception:
            return closed
        for position in positions:
            if self.broker.close_trade(position.trade_id, units=position.units):
                closed += 1
        return closed

    def _trigger_failsafe(self, instrument: Optional[str], reason: str) -> None:
        if self._paused:
            return
        if self.close_on_failsafe:
            closed = self._close_all_positions(instrument=instrument)
            self._alert(f"[runtime] failsafe close_all_positions closed={closed} reason={reason}")
            self._emit_event(
                "runtime.failsafe.close_all",
                {"account_id": self.account_id, "instrument": instrument or "", "closed_positions": closed, "reason": reason},
            )
        self._paused = True
        self._write_pause_marker(reason=reason)
        if self.account_state_machine is not None and self.account_id:
            self.account_state_machine.pause(account_id=self.account_id, reason=reason)
        self._alert(f"[runtime] trading paused reason={reason}")
        self._emit_event(
            "runtime.failsafe.paused",
            {"account_id": self.account_id, "instrument": instrument or "", "reason": reason},
        )

    def trigger_external_failsafe(self, reason: str, instrument: Optional[str] = None) -> None:
        """Allow order lifecycle layer to trigger the same runtime failsafe."""
        self._trigger_failsafe(instrument=instrument, reason=reason)

    def run_step(self, instrument: Optional[str] = None, strategy: str = "unknown") -> RuntimeStepResult:
        now = _utc_now_iso()
        if self.account_state_machine is not None and self.account_id:
            pause_reason = self.account_state_machine.get_pause_reason(self.account_id)
            if pause_reason is not None:
                self._paused = True
                return RuntimeStepResult(
                    timestamp=now,
                    connected=self.broker.is_connected,
                    reconnect_attempts=0,
                    synced_positions=0,
                    mismatch_count=0,
                    mismatch_streak=self._mismatch_streak,
                    failsafe_triggered=False,
                    paused=True,
                    reconciliation={"add": [], "remove": [], "update": []},
                    last_error=f"account_state_blocked:{pause_reason}",
                )
        if self._paused:
            return RuntimeStepResult(
                timestamp=now,
                connected=self.broker.is_connected,
                reconnect_attempts=0,
                synced_positions=0,
                mismatch_count=0,
                mismatch_streak=self._mismatch_streak,
                failsafe_triggered=False,
                paused=True,
                reconciliation={"add": [], "remove": [], "update": []},
                last_error="trading_paused",
            )

        connected, reconnect_attempts, last_error = self._ensure_connected()
        if not connected:
            if self.account_state_machine is not None and self.account_id:
                self.account_state_machine.set_health_state(
                    account_id=self.account_id,
                    health_state="unhealthy",
                    reason=last_error or "connect_failed",
                )
            return RuntimeStepResult(
                timestamp=now,
                connected=False,
                reconnect_attempts=reconnect_attempts,
                synced_positions=0,
                mismatch_count=0,
                mismatch_streak=self._mismatch_streak,
                failsafe_triggered=False,
                paused=False,
                reconciliation={"add": [], "remove": [], "update": []},
                last_error=last_error,
            )

        try:
            broker_positions = self.broker.sync_positions(instrument=instrument)
            if self.account_state_machine is not None and self.account_id:
                self.account_state_machine.set_health_state(
                    account_id=self.account_id,
                    health_state="healthy",
                    reason="runtime_sync_ok",
                )
        except Exception as exc:
            if self.account_state_machine is not None and self.account_id:
                self.account_state_machine.set_health_state(
                    account_id=self.account_id,
                    health_state="unhealthy",
                    reason=f"sync_failed:{exc}",
                )
            return RuntimeStepResult(
                timestamp=now,
                connected=True,
                reconnect_attempts=reconnect_attempts,
                synced_positions=0,
                mismatch_count=0,
                mismatch_streak=self._mismatch_streak,
                failsafe_triggered=False,
                paused=False,
                reconciliation={"add": [], "remove": [], "update": []},
                last_error=f"sync_failed: {exc}",
            )

        local_positions = self.registry.load()
        actions: ReconcileActions = self.validator.reconcile(
            broker_positions=broker_positions,
            local_positions=local_positions,
        )

        mismatch_count = len(actions.add) + len(actions.remove) + len(actions.update)
        if mismatch_count > 0:
            self._mismatch_streak += 1
            self._alert(
                "[runtime] reconciliation actions "
                f"add={len(actions.add)} remove={len(actions.remove)} update={len(actions.update)}"
            )
        else:
            self._mismatch_streak = 0

        self.registry.apply_reconciliation(
            broker_positions=broker_positions,
            local_positions=local_positions,
            actions=actions,
            strategy=strategy,
        )

        failsafe_triggered = False
        if self._mismatch_streak >= self.mismatch_streak_failsafe:
            reason = f"persistent_mismatch_streak={self._mismatch_streak}"
            self._trigger_failsafe(instrument=instrument, reason=reason)
            failsafe_triggered = True

        return RuntimeStepResult(
            timestamp=now,
            connected=True,
            reconnect_attempts=reconnect_attempts,
            synced_positions=len(broker_positions),
            mismatch_count=mismatch_count,
            mismatch_streak=self._mismatch_streak,
            failsafe_triggered=failsafe_triggered,
            paused=self._paused,
            reconciliation={
                "add": actions.add,
                "remove": actions.remove,
                "update": actions.update,
            },
            last_error=None,
        )

    def run_forever(
        self,
        instrument: Optional[str] = None,
        strategy: str = "unknown",
        max_iterations: Optional[int] = None,
    ) -> list[RuntimeStepResult]:
        history: list[RuntimeStepResult] = []
        iterations = 0
        while True:
            iterations += 1
            step = self.run_step(instrument=instrument, strategy=strategy)
            history.append(step)
            self._emit_event(
                "runtime.step",
                {
                    "account_id": self.account_id,
                    "instrument": instrument or "",
                    "connected": step.connected,
                    "reconnect_attempts": step.reconnect_attempts,
                    "synced_positions": step.synced_positions,
                    "mismatch_count": step.mismatch_count,
                    "mismatch_streak": step.mismatch_streak,
                    "failsafe_triggered": step.failsafe_triggered,
                    "paused": step.paused,
                    "last_error": step.last_error,
                },
            )
            if self._paused:
                break
            if max_iterations is not None and iterations >= max_iterations:
                break
            time.sleep(self.poll_interval_seconds)
        return history
