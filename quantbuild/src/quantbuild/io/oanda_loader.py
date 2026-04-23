"""
Oanda Data Loader — historical candles and live streaming.

Replaces yfinance as the primary data source when Oanda broker is configured.
Fetches historical OHLCV data via Oanda v20 Instruments API and stores as Parquet.

Supports:
  - Historical candle fetch (backfill)
  - Incremental updates (append new candles)
  - Automatic Parquet caching
"""
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]

GRANULARITY_MAP = {
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "H1",
    "4h": "H4",
    "1d": "D",
    "1w": "W",
}

MAX_CANDLES_PER_REQUEST = 5000


def _get_oanda_client(token: Optional[str] = None, environment: str = "practice"):
    try:
        import oandapyV20
        tok = token or os.getenv("OANDA_TOKEN", "")
        if not tok:
            raise ValueError("No Oanda token configured. Set OANDA_TOKEN env var.")
        return oandapyV20.API(access_token=tok, environment=environment)
    except ImportError:
        raise ImportError("oandapyV20 not installed. Run: pip install oandapyV20")


def fetch_oanda_candles(
    instrument: str = "XAU_USD",
    granularity: str = "M15",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    count: Optional[int] = None,
    token: Optional[str] = None,
    environment: str = "practice",
) -> pd.DataFrame:
    """Fetch historical candles from Oanda v20 API with pagination."""
    client = _get_oanda_client(token, environment)

    from oandapyV20.endpoints.instruments import InstrumentsCandles

    params: Dict = {"granularity": granularity, "price": "M"}

    if start is not None:
        params["from"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    if end is not None:
        params["to"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
    if count is not None:
        params["count"] = min(count, MAX_CANDLES_PER_REQUEST)

    all_candles = []
    current_start = start

    while True:
        if current_start:
            params["from"] = current_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        if end:
            params["to"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        params["count"] = MAX_CANDLES_PER_REQUEST

        try:
            r = InstrumentsCandles(instrument=instrument, params=params)
            response = client.request(r)
            candles = response.get("candles", [])

            if not candles:
                break

            for c in candles:
                if not c.get("complete", True):
                    continue
                mid = c.get("mid", {})
                all_candles.append({
                    "time": c["time"],
                    "open": float(mid.get("o", 0)),
                    "high": float(mid.get("h", 0)),
                    "low": float(mid.get("l", 0)),
                    "close": float(mid.get("c", 0)),
                    "volume": int(c.get("volume", 0)),
                })

            if len(candles) < MAX_CANDLES_PER_REQUEST:
                break

            last_time = candles[-1]["time"]
            current_start = pd.Timestamp(last_time).to_pydatetime() + timedelta(seconds=1)
            if end and current_start >= end:
                break

        except Exception as e:
            logger.error("Failed to fetch Oanda candles: %s", e)
            break

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time")
    df = df.sort_index()
    df.index = df.index.tz_localize(None)

    logger.info("Fetched %d candles from Oanda (%s %s)", len(df), instrument, granularity)
    return df


def fetch_and_cache(
    instrument: str = "XAU_USD",
    timeframe: str = "15m",
    period_days: int = 90,
    base_path: Optional[Path] = None,
    token: Optional[str] = None,
    environment: str = "practice",
) -> pd.DataFrame:
    """Fetch candles from Oanda and save to Parquet cache (incremental)."""
    granularity = GRANULARITY_MAP.get(timeframe, timeframe.upper())
    cache_dir = (base_path or ROOT / "data" / "market_cache") / "XAUUSD"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{timeframe}.parquet"

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=period_days)

    existing_df = pd.DataFrame()
    if cache_file.exists():
        try:
            existing_df = pd.read_parquet(cache_file)
            if not existing_df.empty:
                last_ts = existing_df.index.max()
                if last_ts is not None:
                    start = pd.Timestamp(last_ts).to_pydatetime() + timedelta(minutes=1)
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=timezone.utc)
                    logger.info("Cache exists up to %s, fetching from %s", last_ts, start)
        except Exception as e:
            logger.warning("Failed to read cache %s: %s", cache_file, e)

    new_df = fetch_oanda_candles(
        instrument=instrument,
        granularity=granularity,
        start=start,
        end=end,
        token=token,
        environment=environment,
    )

    if not existing_df.empty and not new_df.empty:
        df = pd.concat([existing_df, new_df])
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()
    elif not new_df.empty:
        df = new_df
    else:
        df = existing_df

    if not df.empty:
        df.to_parquet(cache_file, engine="pyarrow", compression="snappy")
        logger.info("Saved %d candles to %s", len(df), cache_file)

    return df


def ensure_oanda_data(
    symbol: str = "XAUUSD",
    timeframe: str = "15m",
    base_path: Optional[Path] = None,
    period_days: int = 90,
    token: Optional[str] = None,
    environment: str = "practice",
) -> pd.DataFrame:
    """Drop-in replacement for parquet_loader.ensure_data()."""
    instrument = "XAU_USD" if symbol == "XAUUSD" else symbol.replace("/", "_")
    return fetch_and_cache(
        instrument=instrument,
        timeframe=timeframe,
        period_days=period_days,
        base_path=base_path,
        token=token,
        environment=environment,
    )
