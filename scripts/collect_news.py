"""Collect news events and save to Parquet for backtest replay.

Usage:
    python scripts/collect_news.py --config configs/xauusd.yaml --hours 24
"""
import argparse
import sys
import time
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
    parser.add_argument("--hours", type=float, default=24, help="Hours to collect")
    parser.add_argument("--interval", type=int, default=60, help="Poll interval (seconds)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg)

    poller = NewsPoller(cfg)
    poller.setup()
    relevance_filter = RelevanceFilter(cfg)
    classifier = GoldEventClassifier(cfg)
    sentiment_engine = HybridSentiment(cfg)
    history = NewsHistory()

    print(f"Collecting news for {args.hours}h with {poller.source_count} sources...")
    end_time = time.time() + args.hours * 3600
    total_events = 0

    while time.time() < end_time:
        try:
            events = poller.poll()
            events = relevance_filter.filter_batch(events)

            for event in events:
                classification = classifier.classify(event)
                sentiment = sentiment_engine.analyze(event)
                history.add_event(event, sentiment)
                total_events += 1
                print(f"  [{classification.niche}/{classification.event_type}] "
                      f"{sentiment.direction} ({sentiment.impact_on_gold:+.2f}): "
                      f"{event.headline[:70]}")

            time.sleep(args.interval)
        except KeyboardInterrupt:
            break

    path = history.save_to_parquet()
    history.save_latest_json()
    print(f"\nCollected {total_events} events -> {path}")


if __name__ == "__main__":
    main()
