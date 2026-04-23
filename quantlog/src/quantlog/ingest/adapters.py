"""Adapters for emitting QuantBuild and QuantBridge events."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quantlog.ingest.emitter import EventEmitter


@dataclass(slots=True)
class QuantBuildEmitter:
    emitter: EventEmitter

    @classmethod
    def from_base_path(
        cls,
        base_path: Path,
        source_component: str = "quantbuild_adapter",
        environment: str = "paper",
        run_id: str = "run_default",
        session_id: str = "session_default",
    ) -> "QuantBuildEmitter":
        return cls(
            emitter=EventEmitter(
                base_path=base_path,
                source_system="quantbuild",
                source_component=source_component,
                environment=environment,
                run_id=run_id,
                session_id=session_id,
            )
        )

    def emit(
        self,
        *,
        event_type: str,
        trace_id: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.emitter.emit_event(
            event_type=event_type,
            trace_id=trace_id,
            payload=payload,
            **kwargs,
        )


@dataclass(slots=True)
class QuantBridgeEmitter:
    emitter: EventEmitter

    @classmethod
    def from_base_path(
        cls,
        base_path: Path,
        source_component: str = "quantbridge_adapter",
        environment: str = "paper",
        run_id: str = "run_default",
        session_id: str = "session_default",
    ) -> "QuantBridgeEmitter":
        return cls(
            emitter=EventEmitter(
                base_path=base_path,
                source_system="quantbridge",
                source_component=source_component,
                environment=environment,
                run_id=run_id,
                session_id=session_id,
            )
        )

    def emit(
        self,
        *,
        event_type: str,
        trace_id: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.emitter.emit_event(
            event_type=event_type,
            trace_id=trace_id,
            payload=payload,
            **kwargs,
        )

