"""Ensure every literal ``reason=`` on ``_emit_trade_action(NO_ACTION, ...)`` maps via quantlog_no_action."""

from __future__ import annotations

import ast
from pathlib import Path

from src.quantbuild.execution.quantlog_no_action import (
    _CANONICAL_NO_ACTION,
    canonical_no_action_reason,
)


def _literal_reasons_for_no_action_trade_calls() -> set[str]:
    path = Path(__file__).resolve().parents[1] / "src" / "quantbuild" / "execution" / "live_runner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    collected: list[str] = []

    class V(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "_emit_trade_action":
                kw = {a.arg: a.value for a in node.keywords if a.arg}
                dec = kw.get("decision")
                if isinstance(dec, ast.Constant) and str(dec.value) == "NO_ACTION":
                    r = kw.get("reason")
                    if isinstance(r, ast.Constant) and isinstance(r.value, str):
                        collected.append(r.value)
            self.generic_visit(node)

    V().visit(tree)
    return set(collected)


def test_no_action_literal_reasons_map_to_canonical() -> None:
    literals = _literal_reasons_for_no_action_trade_calls()
    assert literals, "expected AST scan to find _emit_trade_action NO_ACTION literal reasons"
    for lit in literals:
        mapped = canonical_no_action_reason(lit)
        assert mapped in _CANONICAL_NO_ACTION, f"{lit!r} -> {mapped!r} not canonical"


def test_enter_reason_not_accidentally_in_internal_mapping_only() -> None:
    """ENTER uses ``all_conditions_met`` — must not rely on NO_ACTION mapping."""
    assert canonical_no_action_reason("all_conditions_met") == "risk_blocked"
    # ENTER path must keep reason string outside NO_ACTION set (contract elsewhere).
    assert "all_conditions_met" not in _CANONICAL_NO_ACTION
