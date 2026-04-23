"""Message formatters for alerts (Telegram, logs, etc.)."""
from datetime import datetime, timezone
from typing import Any, Dict, List


def format_trade_summary(trades: List[Dict[str, Any]]) -> str:
    if not trades:
        return "No trades today."
    wins = sum(1 for t in trades if t.get("result") == "WIN")
    losses = sum(1 for t in trades if t.get("result") == "LOSS")
    total_r = sum(t.get("profit_r", 0) for t in trades)
    lines = [
        f"Trades: {len(trades)} (W: {wins} / L: {losses})",
        f"Net P&L: {total_r:+.2f}R",
    ]
    return "\n".join(lines)


def format_position_table(positions: List[Dict[str, Any]]) -> str:
    if not positions:
        return "No open positions."
    lines = ["Open Positions:"]
    for p in positions:
        direction = p.get("direction", "?")
        entry = p.get("entry", 0)
        current = p.get("current", 0)
        pnl = p.get("pnl", 0)
        valid = "✓" if p.get("thesis_valid", True) else "✗"
        lines.append(f"  {direction} @ {entry:.2f} → {current:.2f} ({pnl:+.2f}) [{valid}]")
    return "\n".join(lines)


def format_news_digest(events: List[Dict[str, Any]], max_items: int = 10) -> str:
    if not events:
        return "No recent news events."
    lines = [f"Recent News ({len(events)} events):"]
    for ev in events[:max_items]:
        sentiment = ev.get("sentiment", "?")
        headline = ev.get("headline", "")[:60]
        source = ev.get("source", "?")
        lines.append(f"  [{sentiment}] {source}: {headline}")
    return "\n".join(lines)
