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
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _resolve_source_order(source: str) -> tuple[str, list[str]]:
    source_name = str(source or "auto").lower()
    if source_name == "auto":
        return source_name, ["ctrader", "dukascopy", "yfinance"]
    if source_name in {"ctrader", "dukascopy", "yfinance"}:
        return source_name, [source_name]
    logger.warning("Unknown data source '%s'; using auto", source_name)
    return "auto", ["ctrader", "dukascopy", "yfinance"]


def _frame_range_text(df: pd.DataFrame) -> tuple[str, str]:
    if df.empty:
        return "None", "None"
    return str(df.index[0]), str(df.index[-1])


def _tag_source(df: pd.DataFrame, requested: str, actual: str) -> pd.DataFrame:
    """Attach source metadata to returned DataFrame."""
    try:
        df.attrs["source_requested"] = requested
        df.attrs["source_actual"] = actual
    except Exception:
        pass
    return df


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
        elif df.index.tz is None and start_ts.tz is not None:
            start_ts = start_ts.tz_convert("UTC").tz_localize(None)
        df = df[df.index >= start_ts]
    if end is not None:
        end_ts = pd.Timestamp(end)
        if df.index.tz is not None and end_ts.tz is None:
            end_ts = end_ts.tz_localize("UTC")
        elif df.index.tz is None and end_ts.tz is not None:
            end_ts = end_ts.tz_convert("UTC").tz_localize(None)
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
        # FX Metals
        "XAUUSD": inst.INSTRUMENT_FX_METALS_XAU_USD,
        "XAGUSD": inst.INSTRUMENT_FX_METALS_XAG_USD,
        # FX Majors
        "EURUSD": inst.INSTRUMENT_FX_MAJORS_EUR_USD,
        "GBPUSD": inst.INSTRUMENT_FX_MAJORS_GBP_USD,
        "USDJPY": inst.INSTRUMENT_FX_MAJORS_USD_JPY,
        "AUDUSD": inst.INSTRUMENT_FX_MAJORS_AUD_USD,
        "USDCHF": inst.INSTRUMENT_FX_MAJORS_USD_CHF,
        "USDCAD": inst.INSTRUMENT_FX_MAJORS_USD_CAD,
        "NZDUSD": inst.INSTRUMENT_FX_MAJORS_NZD_USD,
        # FX Crosses
        "EURJPY": inst.INSTRUMENT_FX_CROSSES_EUR_JPY,
        "GBPJPY": inst.INSTRUMENT_FX_CROSSES_GBP_JPY,
        "EURGBP": inst.INSTRUMENT_FX_CROSSES_EUR_GBP,
        # Indices
        "US30": inst.INSTRUMENT_IDX_AMERICA_E_D_J_IND,
        "SPX500": inst.INSTRUMENT_IDX_AMERICA_E_SANDP_500,
        "NAS100": inst.INSTRUMENT_IDX_AMERICA_E_NQ_100,
        "GER40": inst.INSTRUMENT_IDX_EUROPE_E_DAAX,
        "UK100": inst.INSTRUMENT_IDX_EUROPE_E_FUTSEE_100,
        "FRA40": inst.INSTRUMENT_IDX_EUROPE_E_CAAC_40,
        "JP225": inst.INSTRUMENT_IDX_ASIA_E_N225JAP,
        "HK50": inst.INSTRUMENT_IDX_ASIA_E_H_KONG,
        "AUS200": inst.INSTRUMENT_IDX_ASIA_E_XJO_ASX,
        # Energy
        "BRENT": inst.INSTRUMENT_CMD_ENERGY_E_BRENT,
        "NGAS": inst.INSTRUMENT_CMD_ENERGY_GAS_CMD_USD,
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


def _normalize_ohlcv_frame(data: Any) -> pd.DataFrame:
    """Normalize arbitrary OHLCV-like payload to canonical DataFrame."""
    if data is None:
        return pd.DataFrame()
    if not isinstance(data, pd.DataFrame):
        try:
            data = pd.DataFrame(data)
        except Exception:
            return pd.DataFrame()
    if data.empty:
        return pd.DataFrame()

    lower_map = {c: str(c).lower() for c in data.columns}
    data = data.rename(columns=lower_map)

    # Common cTrader/adapter aliases.
    aliases = {
        "timestamp": ("timestamp", "time", "datetime", "date"),
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c"),
        "volume": ("volume", "vol", "tick_volume"),
    }
    resolved = {}
    for target, options in aliases.items():
        for name in options:
            if name in data.columns:
                resolved[target] = name
                break

    if not {"open", "high", "low", "close"}.issubset(set(resolved.keys())):
        return pd.DataFrame()

    if "timestamp" in resolved:
        data = data.set_index(resolved["timestamp"])
    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index, errors="coerce", utc=True)
    else:
        data.index = pd.to_datetime(data.index, utc=True)

    data = data[~data.index.isna()].copy()
    if data.empty:
        return pd.DataFrame()

    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    out = pd.DataFrame(index=data.index)
    out["open"] = pd.to_numeric(data[resolved["open"]], errors="coerce")
    out["high"] = pd.to_numeric(data[resolved["high"]], errors="coerce")
    out["low"] = pd.to_numeric(data[resolved["low"]], errors="coerce")
    out["close"] = pd.to_numeric(data[resolved["close"]], errors="coerce")
    if "volume" in resolved:
        out["volume"] = pd.to_numeric(data[resolved["volume"]], errors="coerce").fillna(0.0)
    else:
        out["volume"] = 0.0

    out = out.dropna(subset=["open", "high", "low", "close"]).sort_index()
    return out


def _fetch_ctrader(
    broker: Any,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Fetch OHLCV from cTrader bridge when supported by the broker adapter."""
    if broker is None or not hasattr(broker, "fetch_ohlcv"):
        return pd.DataFrame()
    try:
        raw = broker.fetch_ohlcv(timeframe=timeframe, start=start, end=end, instrument=symbol)
    except Exception as e:
        logger.warning("cTrader OHLCV fetch failed for %s %s: %s", symbol, timeframe, e)
        return pd.DataFrame()
    return _normalize_ohlcv_frame(raw)


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
    source: str = "auto",
    broker: Any = None,
) -> pd.DataFrame:
    """
    Ensure data exists with configurable source routing.
    Supported source values: auto, dukascopy, ctrader, yfinance.
    """
    end = datetime.now()
    start = end - timedelta(days=period_days)
    base_path = Path(base_path)
    existing = load_parquet(base_path, symbol, timeframe, start=start, end=end)

    if len(existing) > 100:
        return existing

    source_requested, source_order = _resolve_source_order(source)
    failure_reasons: list[str] = []

    for provider in source_order:
        try:
            logger.info(
                "data_fetch_attempt requested=%s provider=%s symbol=%s timeframe=%s min_rows=100",
                source_requested, provider, symbol, timeframe,
            )
            if provider == "ctrader":
                data = _fetch_ctrader(broker, symbol, timeframe, start, end)
                if not data.empty and len(data) >= 100:
                    save_parquet(base_path, symbol, timeframe, data)
                    first_ts, last_ts = _frame_range_text(data)
                    logger.info(
                        "data_fetch_success requested=%s actual=%s symbol=%s timeframe=%s rows=%d "
                        "first_ts=%s last_ts=%s",
                        source_requested, provider, symbol, timeframe, len(data), first_ts, last_ts,
                    )
                    return load_parquet(base_path, symbol, timeframe, start=start, end=end)
                failure_reasons.append(f"{provider}: rows={len(data)}")
            elif provider == "dukascopy":
                data = _fetch_dukascopy(symbol, timeframe, start, end)
                if not data.empty and len(data) >= 100:
                    save_parquet(base_path, symbol, timeframe, data)
                    first_ts, last_ts = _frame_range_text(data)
                    logger.info(
                        "data_fetch_success requested=%s actual=%s symbol=%s timeframe=%s rows=%d "
                        "first_ts=%s last_ts=%s",
                        source_requested, provider, symbol, timeframe, len(data), first_ts, last_ts,
                    )
                    return load_parquet(base_path, symbol, timeframe, start=start, end=end)
                failure_reasons.append(f"{provider}: rows={len(data)}")
            elif provider == "yfinance":
                data = _fetch_yfinance(symbol, timeframe, period_days)
                if not data.empty:
                    save_parquet(base_path, symbol, timeframe, data)
                    first_ts, last_ts = _frame_range_text(data)
                    logger.info(
                        "data_fetch_success requested=%s actual=%s symbol=%s timeframe=%s rows=%d "
                        "first_ts=%s last_ts=%s",
                        source_requested, provider, symbol, timeframe, len(data), first_ts, last_ts,
                    )
                    return load_parquet(base_path, symbol, timeframe, start=start, end=end)
                failure_reasons.append(f"{provider}: rows=0")
        except Exception as e:
            failure_reasons.append(f"{provider}: {e}")

    logger.warning(
        "data_fetch_failed requested=%s symbol=%s timeframe=%s reasons=%s",
        source_requested, symbol, timeframe, " | ".join(failure_reasons) if failure_reasons else "n/a",
    )

    return existing


def ensure_live_data(
    symbol: str,
    timeframe: str,
    base_path: Path,
    min_bars: int = 200,
    max_stale_minutes: int = 30,
    source: str = "auto",
    broker: Any = None,
) -> pd.DataFrame:
    """Ensure fresh data for live trading via configurable source routing.

    Returns DataFrame with at least ``min_bars`` rows if data is available,
    empty DataFrame on total failure.
    """
    base_path = Path(base_path)
    now = datetime.now(timezone.utc)
    # Estimate required calendar window from timeframe + min_bars.
    # Markets like XAU trade 5d/week, so we use effective bars/day
    # instead of full 24/7 bars to avoid under-fetch (notably 1h).
    tf = str(timeframe).lower()
    effective_bars_per_day = {
        "1m": 340.0,
        "5m": 68.0,
        "15m": 22.0,
        "30m": 11.0,
        "1h": 17.0,
        "4h": 4.0,
        "1d": 1.0,
    }.get(tf, 22.0)
    period_days = max(10, int(min_bars / max(effective_bars_per_day, 1.0)) + 5)
    start = now - timedelta(days=period_days)

    existing = load_parquet(base_path, symbol, timeframe, start=start, end=now)
    source_name = str(source or "auto").lower()
    truth_mode_ctrader = source_name == "ctrader"

    needs_refresh = False
    if truth_mode_ctrader:
        needs_refresh = True
        logger.info(
            "bootstrap_truth_mode requested=ctrader cache_bypass=true symbol=%s timeframe=%s "
            "reason=broker_native_validation cached_rows=%d",
            symbol, timeframe, len(existing),
        )
    elif existing.empty or len(existing) < min_bars:
        needs_refresh = True
        logger.info(
            "live_data_refresh: %s %s cache has %d bars (need %d)",
            symbol, timeframe, len(existing), min_bars,
        )
    else:
        last_bar = existing.index[-1]
        if hasattr(last_bar, "tz") and last_bar.tz is None:
            last_bar = last_bar.tz_localize("UTC")
        age_minutes = (now - last_bar).total_seconds() / 60
        if age_minutes > max_stale_minutes:
            needs_refresh = True
            logger.info(
                "live_data_refresh: %s %s last bar %.0f min old (max %d)",
                symbol, timeframe, age_minutes, max_stale_minutes,
            )

    if not needs_refresh:
        return _tag_source(existing.tail(min_bars), str(source or "auto").lower(), "cache_fresh")

    source_requested = source_name
    if source_requested == "auto":
        source_order = ["ctrader", "dukascopy"]
    elif source_requested in {"ctrader", "dukascopy"}:
        source_order = [source_requested]
    elif source_requested == "yfinance":
        logger.error(
            "live_data_refresh_invalid_source requested=yfinance symbol=%s timeframe=%s "
            "reason=yfinance_not_allowed_for_live",
            symbol, timeframe,
        )
        return pd.DataFrame()
    else:
        logger.warning("Unknown live data source '%s'; using auto", source_requested)
        source_requested = "auto"
        source_order = ["ctrader", "dukascopy"]

    best_partial: Optional[pd.DataFrame] = None
    best_partial_source: Optional[str] = None
    failure_reasons: list[str] = []

    for provider in source_order:
        try:
            logger.info(
                "live_data_fetch_attempt requested=%s provider=%s symbol=%s timeframe=%s "
                "min_bars=%d window_start=%s window_end=%s",
                source_requested, provider, symbol, timeframe, min_bars, start, now,
            )
            if provider == "ctrader":
                data = _fetch_ctrader(broker, symbol, timeframe, start, now)
            else:
                data = _fetch_dukascopy(symbol, timeframe, start, now)

            if not data.empty and len(data) >= min_bars:
                save_parquet(base_path, symbol, timeframe, data)
                first_ts, last_ts = _frame_range_text(data)
                logger.info(
                    "live_data_refresh_success requested=%s actual=%s symbol=%s timeframe=%s bars=%d "
                    "first_ts=%s last_ts=%s",
                    source_requested, provider, symbol, timeframe, len(data), first_ts, last_ts,
                )
                return _tag_source(data.tail(min_bars), source_requested, provider)
            if not data.empty and (best_partial is None or len(data) > len(best_partial)):
                best_partial = data
                best_partial_source = provider
                save_parquet(base_path, symbol, timeframe, data)
            failure_reasons.append(f"{provider}: rows={len(data)}")
        except Exception as e:
            failure_reasons.append(f"{provider}: {e}")

    # Explicit cTrader mode must fail fast: do not hide venue-data issues.
    if source_requested == "ctrader":
        logger.error(
            "live_data_refresh_fail_fast requested=ctrader symbol=%s timeframe=%s "
            "reasons=%s",
            symbol, timeframe, " | ".join(failure_reasons) if failure_reasons else "n/a",
        )
        return _tag_source(pd.DataFrame(), source_requested, "none")

    if best_partial is not None and not best_partial.empty:
        first_ts, last_ts = _frame_range_text(best_partial)
        logger.warning(
            "live_data_refresh_partial requested=%s actual=%s symbol=%s timeframe=%s "
            "bars=%d need=%d first_ts=%s last_ts=%s",
            source_requested, best_partial_source, symbol, timeframe, len(best_partial), min_bars,
            first_ts, last_ts,
        )
        return _tag_source(best_partial, source_requested, best_partial_source or "unknown")

    if not existing.empty:
        first_ts, last_ts = _frame_range_text(existing)
        logger.warning(
            "live_data_refresh_stale_cache requested=%s actual=cache_stale symbol=%s timeframe=%s "
            "bars=%d first_ts=%s last_ts=%s reasons=%s",
            source_requested, symbol, timeframe, len(existing), first_ts, last_ts,
            " | ".join(failure_reasons) if failure_reasons else "n/a",
        )
        return _tag_source(existing.tail(min_bars), source_requested, "cache_stale")

    logger.error(
        "live_data_refresh_failed requested=%s actual=none symbol=%s timeframe=%s "
        "reasons=%s",
        source_requested, symbol, timeframe, " | ".join(failure_reasons) if failure_reasons else "n/a",
    )
    return _tag_source(pd.DataFrame(), source_requested, "none")
