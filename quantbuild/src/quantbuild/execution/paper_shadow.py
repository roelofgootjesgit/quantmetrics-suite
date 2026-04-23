"""Paper Shadow Mode — run adaptive and static side-by-side on live data.

Every signal gets evaluated twice:
  1. Through the adaptive allocator (what we would actually trade)
  2. Through static rules (the benchmark)

Both decisions are logged with full context for post-hoc comparison.
Neither executes real trades — this is pure observation.

After N days, compare:
  - Per-signal: did adaptive decision improve or hurt?
  - Missed trade PnL: what did the adaptive layer skip?
  - Blocked trade PnL: what did the heat engine prevent?
  - Realized vs expected slippage

This is the ONLY way to validate adaptive benefits before real capital.
"""
import csv
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ShadowDecision:
    """One signal evaluated through both allocators."""
    timestamp: datetime
    symbol: str
    direction: str
    regime: str
    session: str
    signal_pnl_r: float

    # Adaptive decision
    adaptive_action: str       # "TRADE" / "BLOCK" / "SKIP"
    adaptive_risk_pct: float
    adaptive_mode: str
    adaptive_block_reason: str = ""

    # Static decision
    static_action: str         # "TRADE" / "BLOCK"
    static_risk_pct: float
    static_block_reason: str = ""

    # Execution simulation
    slippage_r: float = 0.0
    spread_pips: float = 0.0

    # Outcome (filled after trade resolves)
    adaptive_pnl_pct: float = 0.0
    static_pnl_pct: float = 0.0
    delta_pnl_pct: float = 0.0


class PaperShadowRunner:
    """Dual-track signal evaluator for live paper trading.

    Usage in LiveRunner:
        shadow = PaperShadowRunner(config)

        # On each signal:
        decision = shadow.evaluate(signal, heat_engine, adaptive_layer, ...)
        # decision.adaptive_action tells you what adaptive would do
        # decision.static_action tells you what static would do

        # Periodically:
        shadow.print_scoreboard()
        shadow.save_log()
    """

    def __init__(self, config: Dict[str, Any]):
        self._decisions: List[ShadowDecision] = []
        self._base_risk = config.get("risk_per_trade_pct", 1.5)
        self._log_dir = config.get("shadow_log_dir", "data/shadow_logs")

    def evaluate(
        self,
        symbol: str,
        direction: str,
        regime: str,
        session: str,
        signal_pnl_r: float,
        adaptive_mode: str,
        adaptive_risk_pct: float,
        adaptive_allowed: bool,
        adaptive_block_reason: str,
        static_risk_pct: float,
        static_allowed: bool,
        static_block_reason: str,
        slippage_r: float = 0.0,
        spread_pips: float = 0.0,
    ) -> ShadowDecision:
        """Evaluate a signal through both allocators."""
        adaptive_action = "TRADE" if adaptive_allowed else "BLOCK"
        static_action = "TRADE" if static_allowed else "BLOCK"

        # Lockdown = special block
        if adaptive_mode == "LOCKDOWN":
            adaptive_action = "SKIP"

        # Calculate hypothetical PnL
        adaptive_pnl = (signal_pnl_r - slippage_r) * adaptive_risk_pct if adaptive_allowed else 0.0
        static_pnl = (signal_pnl_r - slippage_r) * static_risk_pct if static_allowed else 0.0

        decision = ShadowDecision(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            direction=direction,
            regime=regime,
            session=session,
            signal_pnl_r=signal_pnl_r,
            adaptive_action=adaptive_action,
            adaptive_risk_pct=adaptive_risk_pct,
            adaptive_mode=adaptive_mode,
            adaptive_block_reason=adaptive_block_reason,
            static_action=static_action,
            static_risk_pct=static_risk_pct,
            static_block_reason=static_block_reason,
            slippage_r=slippage_r,
            spread_pips=spread_pips,
            adaptive_pnl_pct=adaptive_pnl,
            static_pnl_pct=static_pnl,
            delta_pnl_pct=adaptive_pnl - static_pnl,
        )
        self._decisions.append(decision)
        return decision

    @property
    def decisions(self) -> List[ShadowDecision]:
        return list(self._decisions)

    def scoreboard(self) -> Dict[str, Any]:
        """Compute comparison metrics."""
        if not self._decisions:
            return {"signals": 0}

        n = len(self._decisions)
        adaptive_traded = [d for d in self._decisions if d.adaptive_action == "TRADE"]
        static_traded = [d for d in self._decisions if d.static_action == "TRADE"]
        adaptive_blocked = [d for d in self._decisions if d.adaptive_action in ("BLOCK", "SKIP")]

        adaptive_total_pnl = sum(d.adaptive_pnl_pct for d in self._decisions)
        static_total_pnl = sum(d.static_pnl_pct for d in self._decisions)

        # Missed winners: adaptive blocked but signal was profitable
        missed_winners = [d for d in adaptive_blocked if d.signal_pnl_r > 0]
        missed_winner_r = sum(d.signal_pnl_r for d in missed_winners)

        # Avoided losers: adaptive blocked and signal was negative
        avoided_losers = [d for d in adaptive_blocked if d.signal_pnl_r < 0]
        avoided_loser_r = sum(abs(d.signal_pnl_r) for d in avoided_losers)

        # Per-mode stats
        mode_stats = {}
        for d in adaptive_traded:
            mode_stats.setdefault(d.adaptive_mode, {"count": 0, "pnl": 0.0})
            mode_stats[d.adaptive_mode]["count"] += 1
            mode_stats[d.adaptive_mode]["pnl"] += d.adaptive_pnl_pct

        return {
            "signals": n,
            "adaptive_trades": len(adaptive_traded),
            "static_trades": len(static_traded),
            "adaptive_blocks": len(adaptive_blocked),
            "adaptive_total_pnl": round(adaptive_total_pnl, 3),
            "static_total_pnl": round(static_total_pnl, 3),
            "delta_pnl": round(adaptive_total_pnl - static_total_pnl, 3),
            "missed_winners": len(missed_winners),
            "missed_winner_r": round(missed_winner_r, 2),
            "avoided_losers": len(avoided_losers),
            "avoided_loser_r": round(avoided_loser_r, 2),
            "net_block_value_r": round(avoided_loser_r - missed_winner_r, 2),
            "mode_distribution": mode_stats,
        }

    def print_scoreboard(self):
        sb = self.scoreboard()
        print(f"\n  Paper Shadow Scoreboard ({sb['signals']} signals)")
        print(f"  {'='*50}")
        print(f"    Adaptive trades:      {sb['adaptive_trades']}")
        print(f"    Static trades:        {sb['static_trades']}")
        print(f"    Adaptive blocks:      {sb['adaptive_blocks']}")
        print(f"    Adaptive PnL:         {sb['adaptive_total_pnl']:+.3f}%")
        print(f"    Static PnL:           {sb['static_total_pnl']:+.3f}%")
        print(f"    Delta:                {sb['delta_pnl']:+.3f}%")
        print(f"    Missed winners:       {sb['missed_winners']} ({sb['missed_winner_r']:+.2f}R)")
        print(f"    Avoided losers:       {sb['avoided_losers']} ({sb['avoided_loser_r']:+.2f}R)")
        print(f"    Net block value:      {sb['net_block_value_r']:+.2f}R")

        for mode, stats in sb.get("mode_distribution", {}).items():
            avg = stats["pnl"] / stats["count"] if stats["count"] else 0
            print(f"    {mode:>12s}: {stats['count']} trades, PnL {stats['pnl']:+.3f}%, avg {avg:+.4f}%")

    def save_log(self, path: str = ""):
        """Save all decisions to CSV for post-hoc analysis."""
        out = path or os.path.join(self._log_dir, f"shadow_{datetime.utcnow().strftime('%Y%m%d')}.csv")
        os.makedirs(os.path.dirname(out), exist_ok=True)

        with open(out, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "symbol", "direction", "regime", "session",
                "signal_pnl_r", "adaptive_action", "adaptive_risk_pct",
                "adaptive_mode", "adaptive_block_reason",
                "static_action", "static_risk_pct", "static_block_reason",
                "slippage_r", "spread_pips",
                "adaptive_pnl_pct", "static_pnl_pct", "delta_pnl_pct",
            ])
            for d in self._decisions:
                writer.writerow([
                    d.timestamp.isoformat(), d.symbol, d.direction,
                    d.regime, d.session, d.signal_pnl_r,
                    d.adaptive_action, d.adaptive_risk_pct,
                    d.adaptive_mode, d.adaptive_block_reason,
                    d.static_action, d.static_risk_pct, d.static_block_reason,
                    d.slippage_r, d.spread_pips,
                    d.adaptive_pnl_pct, d.static_pnl_pct, d.delta_pnl_pct,
                ])
        logger.info("Shadow log saved: %s (%d decisions)", out, len(self._decisions))
        return out

    def save_scoreboard_json(self, path: str = ""):
        out = path or os.path.join(self._log_dir, f"scoreboard_{datetime.utcnow().strftime('%Y%m%d')}.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(self.scoreboard(), f, indent=2, default=str)
        return out
