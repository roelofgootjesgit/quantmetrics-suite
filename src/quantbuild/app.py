"""CLI entrypoint: backtest, fetch, live, news-test."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from src.quantbuild.config import load_config
from src.quantbuild.logging_config import setup_logging


def cmd_backtest(args: argparse.Namespace) -> int:
    from src.quantbuild.backtest.engine import run_backtest
    cfg = load_config(args.config)
    if getattr(args, "days", None) is not None:
        cfg.setdefault("backtest", {})["default_period_days"] = args.days
    setup_logging(cfg)
    trades = run_backtest(cfg)
    if not trades:
        print("No trades generated.")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    setup_logging(cfg)
    base = Path(cfg.get("data", {}).get("base_path", "data/market_cache"))
    symbol = args.symbol or cfg.get("symbol", "XAUUSD")
    period_days = args.days or cfg.get("backtest", {}).get("default_period_days", 60)
    timeframes = [args.timeframe] if args.timeframe else cfg.get("timeframes", ["15m", "1h"])
    source = getattr(args, "source", "auto")

    for tf in timeframes:
        print(f"Fetching {symbol} {tf} ({period_days}d) via {source}...")

        if source == "dukascopy":
            from src.quantbuild.io.parquet_loader import _fetch_dukascopy, save_parquet
            from datetime import timedelta
            end = datetime.now()
            start = end - timedelta(days=period_days)
            data = _fetch_dukascopy(symbol, tf, start, end)
            if not data.empty:
                save_parquet(base, symbol, tf, data)
                print(f"  Dukascopy: {len(data):,} rows saved")
            else:
                print(f"  Dukascopy: no data returned for {tf}")
        elif source == "oanda":
            from src.quantbuild.io.oanda_loader import fetch_and_cache
            data = fetch_and_cache(timeframe=tf, period_days=period_days, base_path=base)
            print(f"  Oanda: {len(data):,} rows saved")
        else:
            from src.quantbuild.io.parquet_loader import ensure_data
            ensure_data(symbol=symbol, timeframe=tf, base_path=base, period_days=period_days)
    return 0


def cmd_news_test(args: argparse.Namespace) -> int:
    """Test the news layer: poll once and show results."""
    cfg = load_config(args.config)
    setup_logging(cfg)
    from src.quantbuild.news.poller import NewsPoller
    poller = NewsPoller(cfg)
    n_sources = poller.setup()
    print(f"News poller: {n_sources} sources configured")
    events = poller.poll()
    print(f"Polled {len(events)} new events:")
    for ev in events[:20]:
        print(f"  [{ev.source_tier.name}] {ev.source_name}: {ev.headline[:80]}")
        if ev.topic_hints:
            print(f"    topics: {', '.join(ev.topic_hints)}")
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    """Run the bot in live/paper trading mode."""
    cfg = load_config(args.config)
    setup_logging(cfg)
    from src.quantbuild.execution.live_runner import LiveRunner
    runner = LiveRunner(cfg, dry_run=args.dry_run)
    runner.run()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="quantbuild", description="Quantbuild E1 — XAUUSD Trading Bot")
    parser.add_argument("--config", "-c", default=None, help="Path to YAML config")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="Run backtest")
    bt.add_argument("--days", "-d", type=int, default=None)
    bt.set_defaults(func=cmd_backtest)

    fetch = sub.add_parser("fetch", help="Fetch/cache market data")
    fetch.add_argument("--symbol", "-s", default=None)
    fetch.add_argument("--timeframe", "-t", default=None)
    fetch.add_argument("--days", "-d", type=int, default=None)
    fetch.add_argument("--source", choices=["auto", "dukascopy", "oanda", "yfinance"], default="auto",
                        help="Data source (default: auto = dukascopy → yfinance)")
    fetch.set_defaults(func=cmd_fetch)

    news = sub.add_parser("news-test", help="Test news layer (poll once)")
    news.set_defaults(func=cmd_news_test)

    live = sub.add_parser("live", help="Run live/paper trading")
    live.add_argument("--dry-run", action="store_true", default=True, help="Paper trading mode (default)")
    live.add_argument("--real", action="store_true", dest="real", help="Real trading (requires credentials)")
    live.set_defaults(func=cmd_live)

    args = parser.parse_args()
    if hasattr(args, "real") and args.real:
        args.dry_run = False
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
