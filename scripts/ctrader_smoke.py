"""cTrader smoke tests (connect -> price -> place -> close)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.quantbuild.config import load_config
from src.quantbuild.execution.broker_factory import create_broker
from src.quantbuild.execution.symbol_registry import map_symbol


def main() -> int:
    parser = argparse.ArgumentParser(description="cTrader smoke test")
    parser.add_argument("--config", default="configs/ctrader_icmarkets_demo.yaml")
    parser.add_argument("--units", type=float, default=1.0)
    args = parser.parse_args()

    cfg = load_config(args.config)
    broker_cfg = cfg.get("broker", {}) or {}
    provider = str(broker_cfg.get("provider", "ctrader")).lower()
    if provider != "ctrader":
        raise RuntimeError(f"Expected ctrader provider, got: {provider}")

    broker = create_broker(cfg)
    symbol = map_symbol("ctrader", str(cfg.get("symbol", "XAUUSD")))

    results = {
        "connect": False,
        "price": False,
        "place_order": False,
        "close_order": False,
    }

    connected = broker.connect()
    results["connect"] = bool(connected)
    if not connected:
        rb = getattr(broker, "_real_bridge", None)
        results["quantbridge_last_error"] = getattr(rb, "_last_error", None) if rb else None
        if rb is not None:
            client = getattr(rb, "client", None)
            results["client_last_error"] = getattr(client, "last_error", None) if client else None
        print(json.dumps(results, indent=2))
        return 1

    px = broker.get_current_price(symbol)
    results["price"] = px is not None and "ask" in px and "bid" in px
    if not results["price"]:
        print(json.dumps(results, indent=2))
        return 2

    sl = float(px["ask"]) - 5.0
    tp = float(px["ask"]) + 10.0
    order = broker.submit_market_order(
        instrument=symbol,
        direction="BUY",
        units=args.units,
        sl=sl,
        tp=tp,
        comment="ctrader_smoke",
    )
    results["place_order"] = bool(order.success and order.trade_id)
    if not results["place_order"]:
        print(json.dumps(results, indent=2))
        return 3

    closed = broker.close_trade(order.trade_id)
    results["close_order"] = bool(closed)
    print(json.dumps(results, indent=2))
    return 0 if all(results.values()) else 4


if __name__ == "__main__":
    raise SystemExit(main())
