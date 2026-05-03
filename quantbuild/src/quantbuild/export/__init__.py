"""Export helpers for backtest outputs (fallback paths when QuantLog is off)."""

from src.quantbuild.export.trade_r_series import (
    assert_quantlog_inference_policy,
    maybe_write_trade_r_series_fallback,
    write_trade_r_series,
)

__all__ = [
    "assert_quantlog_inference_policy",
    "write_trade_r_series",
    "maybe_write_trade_r_series_fallback",
]
