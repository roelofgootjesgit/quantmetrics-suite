from __future__ import annotations

from quantbridge.risk.account_limits import AccountLimits
from quantbridge.risk.risk_engine import RiskDecision, RiskSnapshot, TradeIntent, clamp, drawdown_pct


class PropGuard:
    """Centralized risk gate for pre-trade and runtime decisions."""

    def __init__(self, limits: AccountLimits) -> None:
        self.limits = limits

    def evaluate(self, intent: TradeIntent, snapshot: RiskSnapshot) -> RiskDecision:
        instrument = str(intent.instrument).upper()
        units = float(intent.units)
        daily_dd = drawdown_pct(snapshot.start_of_day_balance, snapshot.equity)
        total_dd = drawdown_pct(snapshot.start_balance, snapshot.equity)
        metrics = {
            "daily_drawdown_pct": daily_dd,
            "total_drawdown_pct": total_dd,
            "open_risk_pct": float(snapshot.open_risk_pct),
            "open_positions": float(snapshot.open_positions),
        }

        if snapshot.account_breached:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="account_breached",
                code="risk_account_breached",
                trigger_failsafe=True,
                metrics=metrics,
            )
        if snapshot.trading_paused:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="trading_paused",
                code="risk_trading_paused",
                trigger_failsafe=False,
                metrics=metrics,
            )
        if daily_dd >= self.limits.daily_drawdown_limit_pct:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="daily_drawdown_limit_reached",
                code="risk_daily_drawdown",
                trigger_failsafe=True,
                metrics=metrics,
            )
        if total_dd >= self.limits.total_drawdown_limit_pct:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="total_drawdown_limit_reached",
                code="risk_total_drawdown",
                trigger_failsafe=True,
                metrics=metrics,
            )
        if snapshot.open_positions >= self.limits.max_concurrent_positions:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="max_concurrent_positions_reached",
                code="risk_max_positions",
                trigger_failsafe=False,
                metrics=metrics,
            )
        if snapshot.open_risk_pct >= self.limits.max_open_risk_pct:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="max_open_risk_reached",
                code="risk_max_open_risk",
                trigger_failsafe=False,
                metrics=metrics,
            )
        symbol_exposure = float(snapshot.symbol_exposure_pct.get(instrument, 0.0))
        metrics["symbol_exposure_pct"] = symbol_exposure
        if symbol_exposure >= self.limits.symbol_exposure_limit_pct:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="symbol_exposure_limit_reached",
                code="risk_symbol_exposure",
                trigger_failsafe=False,
                metrics=metrics,
            )
        if intent.risk_per_trade_pct is not None and float(intent.risk_per_trade_pct) > self.limits.max_risk_per_trade_pct:
            return RiskDecision(
                allowed=False,
                adjusted_units=0.0,
                reason="risk_per_trade_limit_reached",
                code="risk_per_trade",
                trigger_failsafe=False,
                metrics=metrics,
            )

        adjusted_units = clamp(
            value=units,
            minimum=self.limits.min_units_per_trade,
            maximum=self.limits.max_units_per_trade,
        )
        if adjusted_units != units:
            return RiskDecision(
                allowed=True,
                adjusted_units=adjusted_units,
                reason="units_scaled_to_limits",
                code="risk_scale_units",
                trigger_failsafe=False,
                metrics=metrics,
            )

        return RiskDecision(
            allowed=True,
            adjusted_units=units,
            reason="risk_check_passed",
            code="ok",
            trigger_failsafe=False,
            metrics=metrics,
        )
