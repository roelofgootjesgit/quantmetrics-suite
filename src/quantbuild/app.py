"""CLI entrypoint: backtest, fetch, live, news-test."""
import argparse
import os
import sys
from html import escape
from pathlib import Path

from src.quantbuild.config import load_config, quantbuild_repo_root
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
    broker = None
    if source in {"ctrader", "auto"}:
        try:
            from src.quantbuild.execution.broker_factory import create_broker
            broker = create_broker(cfg)
            broker.connect()
        except Exception:
            broker = None

    try:
        for tf in timeframes:
            print(f"Fetching {symbol} {tf} ({period_days}d) via {source}...")

            if source == "oanda":
                from src.quantbuild.io.oanda_loader import fetch_and_cache
                data = fetch_and_cache(timeframe=tf, period_days=period_days, base_path=base)
                print(f"  Oanda: {len(data):,} rows saved")
                continue

            from src.quantbuild.io.parquet_loader import ensure_data
            data = ensure_data(
                symbol=symbol,
                timeframe=tf,
                base_path=base,
                period_days=period_days,
                source=source,
                broker=broker,
            )
            if data.empty:
                print(f"  No data returned for {symbol} {tf} (source={source})")
            else:
                print(f"  Saved/loaded {len(data):,} rows")
    finally:
        if broker is not None and getattr(broker, "is_connected", False):
            broker.disconnect()
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
    from src.quantbuild.execution.live_runner import LiveRunner
    from src.quantbuild.version import __version__

    mode_line = "DRY_RUN (no broker orders)" if args.dry_run else "REAL (broker orders)"
    cfg_line = str(args.config).replace("\\", "/") if args.config else "(CONFIG_PATH env or configs/default.yaml)"
    sym = cfg.get("symbol", "?")
    broker = cfg.get("broker") or {}
    prov = broker.get("provider", "?")
    dsrc = (cfg.get("data") or {}).get("source", "?")
    bar = "=" * 58
    print(f"\n{bar}", flush=True)
    print(f"  QuantBuild v{__version__}  —  STARTING LIVE", flush=True)
    print(f"  {mode_line}", flush=True)
    print(f"  config: {cfg_line}", flush=True)
    print(f"  symbol={sym}  broker={prov}  data.source={dsrc}", flush=True)
    print(f"{bar}\n", flush=True)

    setup_logging(cfg)
    runner = LiveRunner(cfg, dry_run=args.dry_run)
    runner.run()
    return 0


def cmd_suite_notify(args: argparse.Namespace) -> int:
    """Send suite start/stop Telegram using monitoring.telegram (for QuantMetrics OS orchestrator)."""
    cfg = load_config(args.config)
    setup_logging(cfg)
    from src.quantbuild.alerts.telegram import TelegramAlerter, format_suite_run_summary
    from src.quantbuild.version import __version__, git_revision_short

    alerter = TelegramAlerter(cfg)
    if not alerter.enabled:
        print("Telegram disabled or missing bot_token/chat_id; skipping suite notify.", file=sys.stderr)
        return 0
    comps = [c.strip() for c in args.components if c and str(c).strip()]

    if getattr(args, "real", False):
        execution_mode = "real (orders)"
    elif getattr(args, "dry_run", False):
        execution_mode = "dry_run"
    else:
        execution_mode = os.environ.get("QUANTBUILD_EXECUTION_MODE", "unspecified").strip() or "unspecified"

    version_html = (
        f"<b>QuantBuild</b> v{escape(__version__)} "
        f"<code>(git {escape(git_revision_short())})</code>"
    )
    extra_html = version_html
    if args.config:
        raw = Path(args.config)
        try:
            if raw.is_absolute():
                config_display = str(raw.relative_to(quantbuild_repo_root())).replace("\\", "/")
            else:
                config_display = str(raw).replace("\\", "/")
        except ValueError:
            config_display = str(raw).replace("\\", "/")
        extra_html += "\n\n" + format_suite_run_summary(
            cfg,
            config_path_display=config_display,
            execution_mode=execution_mode,
        )

    if args.event == "start":
        ok = alerter.alert_suite_start(comps, extra_html=extra_html)
    else:
        ok = alerter.alert_suite_stop(
            comps,
            reason=getattr(args, "reason", "") or "",
            extra_html=extra_html,
        )
    if not ok:
        print("Suite notify: Telegram send failed.", file=sys.stderr)
        return 1
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
    fetch.add_argument("--source", choices=["auto", "ctrader", "dukascopy", "oanda", "yfinance"], default="auto",
                        help="Data source (default: auto = ctrader -> dukascopy -> yfinance)")
    fetch.set_defaults(func=cmd_fetch)

    news = sub.add_parser("news-test", help="Test news layer (poll once)")
    news.set_defaults(func=cmd_news_test)

    live = sub.add_parser("live", help="Run live/paper trading")
    live.add_argument("--dry-run", action="store_true", default=True, help="Paper trading mode (default)")
    live.add_argument("--real", action="store_true", dest="real", help="Real trading (requires credentials)")
    live.set_defaults(func=cmd_live)

    sn = sub.add_parser(
        "suite-notify",
        help="Send QuantMetrics suite start/stop to Telegram (uses monitoring.telegram)",
    )
    sn.add_argument("event", choices=["start", "stop"], help="Lifecycle event")
    sn.add_argument(
        "components",
        nargs="+",
        metavar="COMPONENT",
        help="Which parts of the suite are up/down, e.g. build bridge log",
    )
    sn.add_argument("--reason", default="", help="Optional reason (mainly for stop)")
    mode_g = sn.add_mutually_exclusive_group()
    mode_g.add_argument(
        "--dry-run",
        action="store_true",
        help="Label this message as dry_run (matches default `live` without --real)",
    )
    mode_g.add_argument(
        "--real",
        action="store_true",
        help="Label this message as real execution",
    )
    sn.set_defaults(func=cmd_suite_notify)

    args = parser.parse_args()
    if getattr(args, "command", None) == "live" and getattr(args, "real", False):
        args.dry_run = False
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
