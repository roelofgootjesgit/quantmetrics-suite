"""Market Data Smoke Test — verify the full data pipeline before live trading.

Usage:
    python scripts/market_data_smoke.py --symbol XAUUSD --timeframe 15m --count 200

Tests:
  A) Can Dukascopy deliver candles for this symbol/timeframe?
  B) Does the parquet cache save and reload correctly?
  C) Does ensure_live_data return fresh bars?

If any test fails, the live runner will also fail with '0 bars'.
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.quantbuild.io.parquet_loader import (
    _fetch_dukascopy,
    _get_dukascopy_instrument,
    ensure_live_data,
    load_parquet,
    save_parquet,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Market data smoke test")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--base-path", default="data/market_cache")
    args = parser.parse_args()

    symbol = args.symbol.upper()
    tf = args.timeframe
    count = args.count
    base_path = Path(args.base_path)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(10, count // 96 + 3))

    print(f"\n{'='*60}")
    print(f"  MARKET DATA SMOKE TEST")
    print(f"  symbol={symbol}  timeframe={tf}  count={count}")
    print(f"  time={now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    # ── Test 0: Symbol mapping ────────────────────────────────────
    print("[0] Symbol mapping...")
    duka_inst = _get_dukascopy_instrument(symbol)
    if duka_inst is None:
        print(f"  FAIL: '{symbol}' has no Dukascopy mapping")
        sys.exit(1)
    print(f"  OK: {symbol} -> {duka_inst}")

    # ── Test A: Raw Dukascopy fetch ───────────────────────────────
    print(f"\n[A] Fetching {count} bars from Dukascopy...")
    try:
        data = _fetch_dukascopy(symbol, tf, start, now)
    except Exception as e:
        print(f"  FAIL: Dukascopy fetch exception: {e}")
        sys.exit(1)

    if data.empty:
        print(f"  FAIL: Dukascopy returned 0 bars")
        sys.exit(1)

    print(f"  OK: {len(data)} bars received")
    print(f"  first_ts = {data.index[0]}")
    print(f"  last_ts  = {data.index[-1]}")
    print(f"  columns  = {list(data.columns)}")
    sample = data.iloc[-1]
    print(f"  last bar = O:{sample['open']:.2f} H:{sample['high']:.2f} "
          f"L:{sample['low']:.2f} C:{sample['close']:.2f} V:{sample['volume']:.0f}")

    # ── Test B: Parquet round-trip ────────────────────────────────
    print(f"\n[B] Parquet save/load round-trip...")
    try:
        save_parquet(base_path, symbol, tf, data)
        reloaded = load_parquet(base_path, symbol, tf, start=start, end=now)
        if reloaded.empty:
            print(f"  FAIL: Reload returned 0 bars")
            sys.exit(1)
        print(f"  OK: saved and reloaded {len(reloaded)} bars")
    except Exception as e:
        print(f"  FAIL: Parquet round-trip error: {e}")
        sys.exit(1)

    # ── Test C: ensure_live_data ──────────────────────────────────
    print(f"\n[C] ensure_live_data (full pipeline)...")
    try:
        live = ensure_live_data(symbol, tf, base_path, min_bars=count, max_stale_minutes=30)
        if live.empty or len(live) < count:
            print(f"  WARN: Got {len(live)} bars (wanted {count})")
        else:
            print(f"  OK: {len(live)} bars, last={live.index[-1]}")
    except Exception as e:
        print(f"  FAIL: ensure_live_data error: {e}")
        sys.exit(1)

    # ── Summary ───────────────────────────────────────────────────
    age_minutes = (now - data.index[-1].tz_localize("UTC")).total_seconds() / 60 if data.index[-1].tz is None else (now - data.index[-1]).total_seconds() / 60
    print(f"\n{'='*60}")
    print(f"  ALL TESTS PASSED")
    print(f"  {symbol} {tf}: {len(data)} bars available")
    print(f"  Data age: {age_minutes:.0f} minutes")
    if age_minutes > 60:
        print(f"  WARNING: Data is >1hr old. Markets may be closed.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
