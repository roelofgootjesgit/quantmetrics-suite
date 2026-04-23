"""Unit tests for Ops Console normalization (no Streamlit)."""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
for _p in (REPO / "src", REPO / "quantlog_ops"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from services.day_scan import scan_day_jsonl_stats  # noqa: E402
from services.event_loader import load_day_events  # noqa: E402
from services.health import compute_signal_ratios  # noqa: E402
from services.no_trade_explainer import build_no_trade_lines  # noqa: E402
from services.summarizer import summarize  # noqa: E402
from utils.parser import normalize_event  # noqa: E402


class TestOpsNormalize(unittest.TestCase):
    def test_trade_action_no_action_maps_reason(self) -> None:
        ev = {
            "timestamp_utc": "2026-04-19T08:00:00Z",
            "run_id": "r1",
            "event_type": "trade_action",
            "source_system": "quantbuild",
            "severity": "info",
            "payload": {
                "decision": "NO_ACTION",
                "reason": "cooldown_active",
                "session": "London",
                "regime": "trend",
            },
            "symbol": "XAUUSD",
        }
        row = normalize_event(ev)
        self.assertEqual(row["decision"], "NO_ACTION")
        self.assertEqual(row["reason_code"], "cooldown_active")
        self.assertEqual(row["symbol"], "XAUUSD")
        self.assertEqual(row["regime"], "trend")

    def test_no_action_missing_reason_is_unknown(self) -> None:
        ev = {
            "timestamp_utc": "2026-04-19T08:00:00Z",
            "run_id": "r1",
            "event_type": "trade_action",
            "source_system": "quantbuild",
            "severity": "info",
            "payload": {"decision": "NO_ACTION", "reason": ""},
        }
        row = normalize_event(ev)
        self.assertEqual(row["reason_code"], "unknown")

    def test_missing_event_type_is_unknown(self) -> None:
        ev = {
            "timestamp_utc": "2026-04-19T08:00:00Z",
            "run_id": "r1",
            "source_system": "quantbuild",
            "severity": "info",
            "payload": {},
        }
        row = normalize_event(ev)
        self.assertEqual(row["event_type"], "unknown")

    def test_summarize_counts_no_action(self) -> None:
        rows = [
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:00Z",
                    "run_id": "r1",
                    "event_type": "trade_action",
                    "source_system": "quantbuild",
                    "severity": "info",
                    "payload": {
                        "decision": "NO_ACTION",
                        "reason": "no_setup",
                        "regime": "compression",
                    },
                }
            ),
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:01Z",
                    "run_id": "r1",
                    "event_type": "signal_evaluated",
                    "source_system": "quantbuild",
                    "severity": "info",
                    "payload": {"confidence": 0.5, "regime": "expansion"},
                }
            ),
        ]
        s = summarize(rows)
        self.assertEqual(s["total_events"], 2)
        self.assertEqual(s["signals"], 1)
        self.assertEqual(s["no_action"], 1)
        self.assertIn("no_setup", s["by_reason"])

    def test_scan_day_jsonl_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "2026-04-20"
            d.mkdir()
            (d / "a.jsonl").write_text(
                '{"timestamp_utc":"2026-04-20T10:00:00Z","run_id":"r","event_type":"x","payload":{}}\n'
                "{not valid json}\n",
                encoding="utf-8",
            )
            stats = scan_day_jsonl_stats(d)
            self.assertEqual(stats["non_empty_lines"], 2)
            self.assertEqual(stats["parse_failures"], 1)
            self.assertEqual(stats["first_timestamp_utc"], "2026-04-20T10:00:00Z")
            self.assertEqual(stats["last_timestamp_utc"], "2026-04-20T10:00:00Z")

    def test_compute_signal_ratios(self) -> None:
        rows = [
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:00Z",
                    "run_id": "r",
                    "event_type": "signal_evaluated",
                    "source_system": "quantbuild",
                    "severity": "info",
                    "payload": {"confidence": 0.5},
                }
            ),
            normalize_event(
                {
                    "timestamp_utc": "2026-04-19T08:00:01Z",
                    "run_id": "r",
                    "event_type": "trade_action",
                    "source_system": "quantbuild",
                    "severity": "info",
                    "payload": {"decision": "ENTER", "reason": "ok"},
                }
            ),
        ]
        r = compute_signal_ratios(rows)
        self.assertEqual(r["n_signal_evaluated"], 1)
        self.assertEqual(r["ratio_eval_to_trade_action"], 1.0)
        self.assertEqual(r["ratio_eval_to_enter"], 1.0)

    def test_health_metrics_respect_separate_cap(self) -> None:
        """HEALTH vs TABLE caps load different row counts from the same JSONL."""
        import config as cfg

        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "2026-04-21"
            day.mkdir()
            buf: list[str] = []
            for i in range(25):
                buf.append(
                    json.dumps(
                        {
                            "timestamp_utc": f"2026-04-21T10:{i:02d}:00Z",
                            "run_id": "r1",
                            "event_type": "signal_evaluated",
                            "source_system": "quantbuild",
                            "severity": "info",
                            "payload": {"confidence": 0.0, "regime": "trend"},
                        }
                    )
                    + "\n"
                )
            (day / "e.jsonl").write_text("".join(buf), encoding="utf-8")

            try:
                with patch.dict(
                    os.environ,
                    {
                        "QUANTLOG_OPS_HEALTH_MAX_EVENTS": "4",
                        "QUANTLOG_OPS_TABLE_MAX_EVENTS": "20",
                    },
                    clear=False,
                ):
                    importlib.reload(cfg)
                    self.assertEqual(cfg.health_max_events(), 4)
                    self.assertEqual(cfg.table_max_events(), 20)
                    r_h = load_day_events(day, run_id=None, max_events=cfg.health_max_events())
                    r_t = load_day_events(day, run_id=None, max_events=cfg.table_max_events())
                self.assertEqual(len(r_h), 4)
                self.assertEqual(summarize(r_h)["total_events"], 4)
                self.assertEqual(len(r_t), 20)
            finally:
                for key in ("QUANTLOG_OPS_HEALTH_MAX_EVENTS", "QUANTLOG_OPS_TABLE_MAX_EVENTS"):
                    os.environ.pop(key, None)
                importlib.reload(cfg)

    def test_explainer_truncation_note_when_cap_reached(self) -> None:
        lines = build_no_trade_lines(
            summary={"entries": 0, "by_reason": {}},
            rows=[],
            scan=None,
            cap_hit=True,
        )
        self.assertTrue(any("No-trade explainer truncated" in ln for ln in lines))


if __name__ == "__main__":
    unittest.main()
