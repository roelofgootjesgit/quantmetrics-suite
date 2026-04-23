"""Live scan watcher for safe launcher logs.

Shows:
- runtime and heartbeat health
- reconcile scan throughput + latency
- latest signal/decision context
- block reasons (spread/news/risk/limits)
- position sync and trade registration events
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import time
from typing import Dict, List, Optional


TIMESTAMP_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
HEARTBEAT_RE = re.compile(r"Heartbeat \| pid=(?P<pid>\d+) \| elapsed=(?P<elapsed>\d+)s .* status=(?P<status>\w+)")
REQUEST_RE = re.compile(r"request_id=(?P<rid>qb-[0-9a-f]+) payload=(?P<payload>\w+)")
SIGNAL_RE = re.compile(r"SIGNAL:\s*(?P<content>.+)$")


@dataclass
class ScanSummary:
    last_heartbeat_ts: Optional[datetime] = None
    last_heartbeat_elapsed: Optional[int] = None
    last_heartbeat_status: str = "unknown"
    last_signal: str = "-"
    last_trade_registered: str = "-"
    last_sync_event: str = "-"
    block_events: List[str] = None  # type: ignore[assignment]
    reconcile_count: int = 0
    reconcile_avg_latency_ms: float = 0.0
    reconcile_p95_latency_ms: float = 0.0
    reconnect_count: int = 0
    error_count: int = 0
    warning_count: int = 0

    def __post_init__(self) -> None:
        if self.block_events is None:
            self.block_events = []


def parse_ts(line: str) -> Optional[datetime]:
    m = TIMESTAMP_RE.search(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S,%f")
    except Exception:
        return None


def format_age(ts: Optional[datetime]) -> str:
    if ts is None:
        return "n/a"
    delta = datetime.now() - ts
    s = max(0, int(delta.total_seconds()))
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s // 60}m {s % 60}s ago"
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h}h {m}m ago"


def pick_latest_log(log_dir: Path) -> Optional[Path]:
    logs = sorted(log_dir.glob("safe_live_launch_*.log"), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


def compute_summary(lines: List[str]) -> ScanSummary:
    out = ScanSummary()
    req_times: Dict[str, datetime] = {}
    latencies: List[float] = []

    for line in lines:
        ts = parse_ts(line)
        if " | WARNING | " in line:
            out.warning_count += 1
        if " | ERROR | " in line or "Traceback" in line:
            out.error_count += 1
        if "Connected to cTrader OpenAPI via QuantBridge adapter" in line:
            out.reconnect_count += 1

        hb = HEARTBEAT_RE.search(line)
        if hb and ts is not None:
            out.last_heartbeat_ts = ts
            out.last_heartbeat_elapsed = int(hb.group("elapsed"))
            out.last_heartbeat_status = hb.group("status")

        sig = SIGNAL_RE.search(line)
        if sig:
            out.last_signal = sig.group("content").strip()

        if "Trade registered:" in line:
            out.last_trade_registered = line.strip()
        if "Synced position from broker:" in line:
            out.last_sync_event = line.strip()

        if (
            "NewsGate blocks" in line
            or "Spread guard blocks entry" in line
            or "Position limit reached" in line
            or "Daily loss limit reached" in line
            or "Insufficient data for signals" in line
        ):
            out.block_events.append(line.strip())
            if len(out.block_events) > 8:
                out.block_events = out.block_events[-8:]

        if "ctrader.request action=send" in line and "ProtoOAReconcileReq" in line and ts is not None:
            req = REQUEST_RE.search(line)
            if req:
                req_times[req.group("rid")] = ts

        if "ctrader.response action=recv" in line and "ProtoOAReconcileRes" in line and ts is not None:
            req = REQUEST_RE.search(line)
            if req:
                rid = req.group("rid")
                t0 = req_times.pop(rid, None)
                if t0 is not None:
                    latencies.append((ts - t0).total_seconds() * 1000.0)

    out.reconcile_count = len(latencies)
    if latencies:
        lat_sorted = sorted(latencies)
        out.reconcile_avg_latency_ms = sum(lat_sorted) / len(lat_sorted)
        p95_idx = max(0, min(len(lat_sorted) - 1, int(round(0.95 * (len(lat_sorted) - 1)))))
        out.reconcile_p95_latency_ms = lat_sorted[p95_idx]
    return out


def render(summary: ScanSummary, log_file: Path, line_count: int) -> str:
    hb_elapsed = f"{summary.last_heartbeat_elapsed}s" if summary.last_heartbeat_elapsed is not None else "n/a"
    blocks = summary.block_events[-5:] if summary.block_events else []

    rows = [
        "",
        f"Live Scan Monitor | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"log: {log_file}",
        "-" * 92,
        f"Heartbeat      : {summary.last_heartbeat_status} | runner_elapsed={hb_elapsed} | last={format_age(summary.last_heartbeat_ts)}",
        f"Log Health      : lines={line_count} | warnings={summary.warning_count} | errors={summary.error_count} | reconnects={summary.reconnect_count}",
        f"Scan/Reconcile  : cycles={summary.reconcile_count} | avg={summary.reconcile_avg_latency_ms:.0f} ms | p95={summary.reconcile_p95_latency_ms:.0f} ms",
        f"Last Signal     : {summary.last_signal}",
        f"Last Trade Reg  : {summary.last_trade_registered}",
        f"Last Sync Event : {summary.last_sync_event}",
        "-" * 92,
        "Recent Block/Decision Context:",
    ]
    if not blocks:
        rows.append("  - (none recently)")
    else:
        for b in blocks:
            rows.append(f"  - {b}")
    rows.append("-" * 92)
    rows.append("Tip: Ctrl+C to stop watching.")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch safe live scan activity with extra context.")
    parser.add_argument("--log-file", default="", help="Path to safe_live_launch log file")
    parser.add_argument("--log-dir", default="logs", help="Directory to auto-pick latest safe launch log")
    parser.add_argument("--interval-seconds", type=float, default=5.0, help="Refresh interval in follow mode")
    parser.add_argument("--lines", type=int, default=2000, help="Only parse last N lines (0 = all)")
    parser.add_argument("--once", action="store_true", help="Print one snapshot and exit")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear screen on refresh")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if args.log_file:
        log_file = Path(args.log_file)
        if not log_file.is_absolute():
            log_file = root / log_file
    else:
        log_dir = Path(args.log_dir)
        if not log_dir.is_absolute():
            log_dir = root / log_dir
        log_file = pick_latest_log(log_dir) if log_dir.exists() else None
        if log_file is None:
            print(f"No safe launch logs found in: {log_dir}")
            return 2

    if not log_file.exists():
        print(f"Log file does not exist: {log_file}")
        return 2

    interval = max(1.0, float(args.interval_seconds))
    parse_lines = max(0, int(args.lines))

    while True:
        raw = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = raw[-parse_lines:] if parse_lines > 0 else raw
        summary = compute_summary(lines)
        if not args.no_clear:
            # ANSI clear screen; useful in terminals that support it.
            print("\033[2J\033[H", end="")
        print(render(summary, log_file=log_file, line_count=len(raw)))
        sys.stdout.flush()
        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
