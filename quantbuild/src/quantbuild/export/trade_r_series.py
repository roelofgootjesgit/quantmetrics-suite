"""Fallback export of per-trade R when QuantLog JSONL is disabled."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from src.quantbuild.execution.quantlog_ids import resolve_quantlog_run_id
from src.quantbuild.models.trade import Trade
from src.quantbuild.quantlog_repo import quantbuild_project_root

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def quantlog_runs_dir(cfg: dict[str, Any]) -> Path:
    """Directory where consolidated ``{run_id}.jsonl`` and fallback series are stored."""
    ql_cfg = cfg.get("quantlog", {}) or {}
    raw = Path(str(ql_cfg.get("base_path", "data/quantlog_events")))
    ql_base = raw.resolve() if raw.is_absolute() else (quantbuild_project_root() / raw).resolve()
    return (ql_base / "runs").resolve()


def write_trade_r_series(
    trades: list[Trade],
    trade_refs: list[str],
    run_id: str,
    output_dir: Path,
) -> Path:
    """Write ``{run_id}_trade_r_series.json`` (same R ordering as closed trades / JSONL emitter)."""
    if len(trade_refs) != len(trades):
        raise ValueError(f"trade_refs length {len(trade_refs)} != trades length {len(trades)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "trade_r_series_v1",
        "run_id": run_id,
        "generated_at_utc": _utcnow_iso(),
        "source": "trade_object_list",
        "trades": [
            {
                "trade_id": ref,
                "pnl_r": float(t.profit_r),
                "direction": str(getattr(t.direction, "value", t.direction)),
                "open_time": t.timestamp_open.isoformat().replace("+00:00", "Z"),
                "close_time": t.timestamp_close.isoformat().replace("+00:00", "Z"),
            }
            for ref, t in zip(trade_refs, trades)
        ],
    }
    path = output_dir / f"{run_id}_trade_r_series.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote trade R fallback series: %s (n=%d)", path, len(trades))
    return path


def assert_quantlog_inference_policy(cfg: dict[str, Any]) -> None:
    """Raise if config demands QuantLog for inference workflows but logging is off."""
    ql_cfg = cfg.get("quantlog", {}) or {}
    if bool(ql_cfg.get("inference_requires_quantlog", False)) and not bool(ql_cfg.get("enabled", True)):
        raise ValueError(
            "quantlog.enabled is false but quantlog.inference_requires_quantlog is true; "
            "enable QuantLog or set inference_requires_quantlog to false for this run."
        )


def maybe_write_trade_r_series_fallback(
    cfg: dict[str, Any],
    trades: list[Trade],
    trade_refs: list[str],
) -> Path | None:
    """If QuantLog is off and there are trades, persist per-trade R next to the JSONL location."""
    ql_cfg = cfg.get("quantlog", {}) or {}
    if bool(ql_cfg.get("enabled", True)):
        return None
    if not trades:
        return None
    run_id = resolve_quantlog_run_id(ql_cfg)
    out_dir = quantlog_runs_dir(cfg)
    return write_trade_r_series(trades, trade_refs, run_id, out_dir)
