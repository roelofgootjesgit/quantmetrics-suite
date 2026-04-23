from __future__ import annotations

import unittest
from pathlib import Path

from quantlog.validate.validator import validate_path


class TestContracts(unittest.TestCase):
    def test_quantbuild_contract_fixture_validates(self) -> None:
        path = Path("tests/fixtures/contracts/quantbuild_dry_run.jsonl")
        report = validate_path(path)
        errors = [issue for issue in report.issues if issue.level == "error"]
        self.assertEqual(len(errors), 0)

    def test_quantbridge_contract_fixture_validates(self) -> None:
        path = Path("tests/fixtures/contracts/quantbridge_dry_run.jsonl")
        report = validate_path(path)
        errors = [issue for issue in report.issues if issue.level == "error"]
        self.assertEqual(len(errors), 0)

    def test_contracts_directory_quantbuild_plus_quantbridge(self) -> None:
        """Cross-file linkage: ENTER trade_id matches bridge orders (same decision_cycle_id)."""
        path = Path("tests/fixtures/contracts")
        report = validate_path(path)
        errors = [issue for issue in report.issues if issue.level == "error"]
        self.assertEqual(len(errors), 0)


if __name__ == "__main__":
    unittest.main()

