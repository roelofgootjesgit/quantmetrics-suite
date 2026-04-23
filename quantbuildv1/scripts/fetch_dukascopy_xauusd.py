"""
Fetch XAUUSD historical candles from Dukascopy and save as Parquet.

Writes files to data/market_cache/XAUUSD/{5m,15m,1h}.parquet — drop-in
compatible with the existing parquet_loader / backtest engine.

Usage:
    python scripts/fetch_dukascopy_xauusd.py              # default: 1825 days (5 years)
    python scripts/fetch_dukascopy_xauusd.py --days 365   # custom range
    python scripts/fetch_dukascopy_xauusd.py --tf 15m 1h  # specific timeframes
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import dukascopy_python as duka
from dukascopy_python.instruments import INSTRUMENT_FX_METALS_XAU_USD

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "market_cache" / "XAUUSD"

INTERVAL_MAP = {
    "5m": duka.INTERVAL_MIN_5,
    "15m": duka.INTERVAL_MIN_15,
    "1h": duka.INTERVAL_HOUR_1,
}


def fetch_timeframe(
    timeframe: str,
    interval: str,
    start: datetime,
    end: datetime,
) -> None:
    """Download one timeframe from Dukascopy and write Parquet."""
    print(f"[dukascopy] Fetching {timeframe} from {start.date()} to {end.date()} ...")

    df: pd.DataFrame = duka.fetch(
        instrument=INSTRUMENT_FX_METALS_XAU_USD,
        interval=interval,
        offer_side=duka.OFFER_SIDE_BID,
        start=start,
        end=end,
    )

    if df is None or df.empty:
        print(f"[dukascopy] WARNING: no data returned for {timeframe}")
        return

    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index, utc=True)

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df = df.sort_index()

    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            raise ValueError(f"Missing expected column '{col}' in Dukascopy data")

    df = df[["open", "high", "low", "close", "volume"]]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CACHE_DIR / f"{timeframe}.parquet"
    df.to_parquet(out_path, engine="pyarrow", compression="snappy")
    print(f"[dukascopy] Wrote {len(df):,} rows -> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch XAUUSD from Dukascopy")
    parser.add_argument(
        "--days", type=int, default=1825,
        help="Number of days of history (default: 1825 = 5 years)",
    )
    parser.add_argument(
        "--tf", nargs="+", default=["5m", "15m", "1h"],
        help="Timeframes to fetch (default: 5m 15m 1h)",
    )
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=args.days)

    for tf in args.tf:
        interval = INTERVAL_MAP.get(tf)
        if interval is None:
            print(f"[dukascopy] Unknown timeframe '{tf}', skipping")
            continue
        fetch_timeframe(tf, interval, start, end)

    print(f"[dukascopy] Done. Files in: {CACHE_DIR}")


if __name__ == "__main__":
    main()
