"""Suite Telegram summary formatting."""

from src.quantbuild.alerts.telegram import format_suite_run_summary


def test_format_suite_run_summary_escapes_html():
    cfg = {
        "symbol": "XAU<USD>",
        "broker": {"provider": "ctrader", "environment": "demo", "instrument": "XAUUSD"},
        "data": {"source": "ctrader"},
        "quantlog": {"enabled": True, "base_path": "data/x", "run_id": "r1"},
        "strategy": {"name": "sqe"},
        "execution_guards": {"max_open_positions": 3},
        "filters": {"regime": True, "news": False},
    }
    out = format_suite_run_summary(
        cfg,
        config_path_display="configs/demo_strict_ctrader.yaml",
        execution_mode="dry_run",
    )
    assert "XAU&lt;USD&gt;" in out
    assert "demo_strict_ctrader.yaml" in out
    assert "ctrader" in out
