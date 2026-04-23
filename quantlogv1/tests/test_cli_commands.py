from __future__ import annotations

import argparse
import io
import json
import unittest
from contextlib import redirect_stdout

from quantlog.cli import (
    cmd_export_v1_schema,
    cmd_list_envelope_schema,
    cmd_list_event_types,
    cmd_list_no_action_reasons,
)


class TestCliCommands(unittest.TestCase):
    def test_list_no_action_reasons_outputs_sorted_json(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_list_no_action_reasons(argparse.Namespace())
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("core", data)
        self.assertIn("extended", data)
        self.assertIn("all_allowed", data)
        self.assertEqual(data["all_allowed"], sorted(data["all_allowed"]))
        self.assertIn("cooldown_active", data["all_allowed"])
        self.assertIn("no_setup", data["core"])

    def test_list_event_types_includes_trade_action_contract(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_list_event_types(argparse.Namespace())
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("trade_action", data["event_types"])
        self.assertIn("decision", data["payload_contracts"]["trade_action"])
        self.assertIn("reason", data["payload_contracts"]["trade_action"])
        self.assertIn("signal_detected", data["event_types"])
        self.assertIn("signal_filtered", data["event_types"])
        self.assertIn("trade_executed", data["event_types"])
        self.assertIn("market_data_stale_warning", data["event_types"])
        self.assertIn("signal_id", data["payload_contracts"]["signal_detected"])
        self.assertIn("trade_id", data["payload_contracts"]["order_submitted"])
        self.assertIn("trade_id", data["payload_contracts"]["order_filled"])

    def test_list_envelope_schema_has_core_enums(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_list_envelope_schema(argparse.Namespace())
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertIn("run_id", data["required_envelope_fields"])
        self.assertIn("live", data["allowed_environments"])
        self.assertIn("quantbuild", data["allowed_source_systems"])
        self.assertIn("NO_ACTION", data["trade_action_decisions"])
        self.assertIn("LONG", data["trade_executed_directions"])

    def test_export_v1_schema_merges_envelope_events_and_reasons(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmd_export_v1_schema(argparse.Namespace())
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["schema_id"], "quantlog_v1")
        self.assertIn("trade_action", data["event_types"]["payload_contracts"])
        self.assertIn("no_setup", data["no_action_reasons"]["core"])
        self.assertIn("run_id", data["envelope"]["required_fields"])
        self.assertIn("LONG", data["envelope"]["trade_executed_directions"])
        opt = data["signal_evaluated_optional"]
        self.assertIn("payload_keys", opt)
        self.assertIn("gate_summary", opt["payload_keys"])
        self.assertIn("pass", opt["gate_summary_statuses"])
        self.assertIn("structure", opt["combo_module_labels"])


if __name__ == "__main__":
    unittest.main()
