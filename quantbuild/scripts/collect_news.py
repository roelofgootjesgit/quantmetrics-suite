"""Collect news events and save to Parquet for backtest replay.

Supports incremental collection: loads existing history and appends new events.

Usage:
    python scripts/collect_news.py --config configs/xauusd.yaml --hours 24
    python scripts/collect_news.py --continuous   # run indefinitely
"""
import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.quantbuild.config import load_config
from src.quantbuild.logging_config import setup_logging
from src.quantbuild.news.poller import NewsPoller
from src.quantbuild.news.relevance_filter import RelevanceFilter
from src.quantbuild.news.gold_classifier import GoldEventClassifier
from src.quantbuild.news.sentiment import HybridSentiment
from src.quantbuild.news.history import NewsHistory


def main():
    parser = argparse.ArgumentParser(description="Collect news for historical backtest data")
    parser.add_argument("--config", "-c", default="configs/xauusd.yaml")
    parser.add_argument("--hours", type=float, default=24, help="Hours to collect (ignored with --continuous)")
    parser.add_argument("--interval", type=int, default=60, help="Poll interval (seconds)")
    parser.add_argument("--continuous", action="store_true", help="Run indefinitely, saving every 100 events")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg)

    poller = NewsPoller(cfg)
    poller.setup()
    relevance_filter = RelevanceFilter(cfg)
    classifier = GoldEventClassifier(cfg)
    sentiment_engine = HybridSentiment(cfg)
    history = NewsHistory()

    existing = history.load_from_parquet()
    if existing:
        print(f"Loaded {existing} existing events from history")

    mode = "continuous" if args.continuous else f"{args.hours}h"
    print(f"Collecting news ({mode}) with {poller.source_count} sources, interval={args.interval}s")

    end_time = None if args.continuous else time.time() + args.hours * 3600
    total_new = 0
    save_interval = 100

    try:
        while True:
            if end_time and time.time() >= end_time:
                break

            try:
                events = poller.poll()
                events = relevance_filter.filter_batch(events)

                for event in events:
                    classification = classifier.classify(event)
                    sentiment = sentiment_engine.analyze(event)
                    history.add_event(event, sentiment)
                    total_new += 1

                    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
                    print(f"  [{now_str}] [{classification.niche}/{classification.event_type}] "
                          f"{sentiment.direction} ({sentiment.impact_on_gold:+.2f}): "
                          f"{event.headline[:70]}")

                if total_new > 0 and total_new % save_interval == 0:
                    history.save_to_parquet()
                    history.save_latest_json()
                    print(f"  -- checkpoint: {history.event_count} total events saved")

                time.sleep(args.interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"  Error: {e}")
                time.sleep(args.interval)
    finally:
        path = history.save_to_parquet()
        history.save_latest_json()
        print(f"\nSession: +{total_new} new events | Total: {history.event_count} events -> {path}")


if __name__ == "__main__":
    main()
