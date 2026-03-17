"""
Load/save OHLCV DataFrames as Parquet.

Paths: base_path/SYMBOL/timeframe.parquet

Data source priority:
  1. Existing Parquet cache
  2. Dukascopy (free, up to 10+ years of history)
  3. yfinance (fallback, limited to 60d for intraday)
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def path_for(base_path: Path, symbol: str, timeframe: str) -> Path:
    return Path(base_path) / symbol.upper() / f"{timeframe}.parquet"


def load_parquet(
    base_path: Path,
    symbol: str,
    timeframe: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> pd.DataFrame:
    p = path_for(base_path, symbol, timeframe)
    if not p.exists():
        return pd.DataFrame()

    df = pd.read_parquet(p)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index)

    if start is not None:
        start_ts = pd.Timestamp(start)
        if df.index.tz is not None and start_ts.tz is None:
            start_ts = start_ts.tz_localize("UTC")
        df = df[df.index >= start_ts]
    if end is not None:
        end_ts = pd.Timestamp(end)
        if df.index.tz is not None and end_ts.tz is None:
            end_ts = end_ts.tz_localize("UTC")
        df = df[df.index <= end_ts]
    return df


def save_parquet(base_path: Path, symbol: str, timeframe: str, data: pd.DataFrame) -> None:
    p = path_for(base_path, symbol, timeframe)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not isinstance(data.index, pd.DatetimeIndex) and "timestamp" in data.columns:
        data = data.set_index("timestamp")
    data.index = pd.to_datetime(data.index)
    data = data.sort_index()
    data.to_parquet(p, compression="snappy")


def _get_dukascopy_instrument(symbol: str):
    """Map our symbol names to Dukascopy instrument constants."""
    import dukascopy_python.instruments as inst
    mapping = {
        "XAUUSD": inst.INSTRUMENT_FX_METALS_XAU_USD,
        "XAGUSD": inst.INSTRUMENT_FX_METALS_XAG_USD,
        "EURUSD": inst.INSTRUMENT_FX_MAJORS_EUR_USD,
        "GBPUSD": inst.INSTRUMENT_FX_MAJORS_GBP_USD,
        "USDJPY": inst.INSTRUMENT_FX_MAJORS_USD_JPY,
        "AUDUSD": inst.INSTRUMENT_FX_MAJORS_AUD_USD,
        "USDCHF": inst.INSTRUMENT_FX_MAJORS_USD_CHF,
        "USDCAD": inst.INSTRUMENT_FX_MAJORS_USD_CAD,
        "NZDUSD": inst.INSTRUMENT_FX_MAJORS_NZD_USD,
        "EURJPY": inst.INSTRUMENT_FX_CROSSES_EUR_JPY,
        "GBPJPY": inst.INSTRUMENT_FX_CROSSES_GBP_JPY,
        "EURGBP": inst.INSTRUMENT_FX_CROSSES_EUR_GBP,
    }
    return mapping.get(symbol.upper())


def _fetch_dukascopy(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Fetch OHLCV data from Dukascopy (free, multi-year history)."""
    import dukascopy_python as duka

    interval_map = {
        "5m": duka.INTERVAL_MIN_5,
        "15m": duka.INTERVAL_MIN_15,
        "1h": duka.INTERVAL_HOUR_1,
    }
    interval = interval_map.get(timeframe)
    if interval is None:
        raise ValueError(f"Dukascopy: unsupported timeframe '{timeframe}'")

    instrument = _get_dukascopy_instrument(symbol)
    if instrument is None:
        raise ValueError(f"Dukascopy: unsupported symbol '{symbol}'")

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    df = duka.fetch(
        instrument=instrument,
        interval=interval,
        offer_side=duka.OFFER_SIDE_BID,
        start=start,
        end=end,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    if not isinstance(df.index, pd.DatetimeIndex):
        if "timestamp" in df.columns:
            df = df.set_index("timestamp")
        df.index = pd.to_datetime(df.index, utc=True)

    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df = df.sort_index()
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            return pd.DataFrame()
    return df[["open", "high", "low", "close", "volume"]]


def _fetch_yfinance(
    symbol: str,
    timeframe: str,
    period_days: int,
) -> pd.DataFrame:
    """Fetch OHLCV data from yfinance (limited to 60d for intraday)."""
    try:
        import yfinance as yf
    except ImportError:
        return pd.DataFrame()

    ticker = "GC=F" if symbol.upper() == "XAUUSD" else f"{symbol}=X"
    interval = {"1h": "1h", "15m": "15m", "5m": "5m"}.get(timeframe, "15m")
    period = "60d" if period_days <= 60 else "3mo"
    data = yf.download(tickers=ticker, period=period, interval=interval, progress=False, auto_adjust=True)
    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [c[0].lower() for c in data.columns]
    else:
        data.columns = [c.lower() for c in data.columns]
    for col in ["open", "high", "low", "close"]:
        if col not in data.columns:
            return pd.DataFrame()
    if "volume" not in data.columns:
        data["volume"] = 0

    data.index = pd.to_datetime(data.index)
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)
    return data[["open", "high", "low", "close", "volume"]]


def ensure_data(
    symbol: str,
    timeframe: str,
    base_path: Path,
    period_days: int = 60,
) -> pd.DataFrame:
    """
    Ensure data exists. Fetch priority: Dukascopy → yfinance.
    Dukascopy supports years of free intraday data.
    """
    end = datetime.now()
    start = end - timedelta(days=period_days)
    base_path = Path(base_path)
    existing = load_parquet(base_path, symbol, timeframe, start=start, end=end)

    if len(existing) > 100:
        return existing

    # Try Dukascopy first (free, years of data)
    try:
        logger.info("Fetching %s %s via Dukascopy (%dd)...", symbol, timeframe, period_days)
        data = _fetch_dukascopy(symbol, timeframe, start, end)
        if not data.empty and len(data) > 100:
            save_parquet(base_path, symbol, timeframe, data)
            logger.info("Dukascopy: saved %d rows for %s %s", len(data), symbol, timeframe)
            return load_parquet(base_path, symbol, timeframe, start=start, end=end)
    except Exception as e:
        logger.warning("Dukascopy fetch failed: %s — falling back to yfinance", e)

    # Fallback to yfinance
    try:
        logger.info("Fetching %s %s via yfinance (%dd)...", symbol, timeframe, period_days)
        data = _fetch_yfinance(symbol, timeframe, period_days)
        if not data.empty:
            save_parquet(base_path, symbol, timeframe, data)
            logger.info("yfinance: saved %d rows for %s %s", len(data), symbol, timeframe)
            return load_parquet(base_path, symbol, timeframe, start=start, end=end)
    except Exception as e:
        logger.warning("yfinance fetch failed: %s", e)

    return existing
