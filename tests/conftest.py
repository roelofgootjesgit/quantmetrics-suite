"""Pytest hooks: disable optional QuantAnalytics subprocess during unit tests."""

import pytest


@pytest.fixture(autouse=True)
def _disable_quantanalytics_post_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid spawning ``quantmetrics_analytics`` from backtests unless a test overrides this."""
    monkeypatch.setenv("QUANTMETRICS_ANALYTICS_AUTO", "0")
