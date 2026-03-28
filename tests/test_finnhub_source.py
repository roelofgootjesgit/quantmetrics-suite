"""Tests for Finnhub news source wiring."""

from src.quantbuild.news.finnhub_source import create_finnhub_source


def test_create_finnhub_source_enabled():
    cfg = {
        "news": {
            "finnhub_api_key": "abc",
            "sources": {"finnhub": {"enabled": True, "category": "general", "tier": 2}},
        }
    }
    source = create_finnhub_source(cfg)
    assert source is not None
    assert source.name == "Finnhub"


def test_create_finnhub_source_disabled():
    cfg = {"news": {"finnhub_api_key": "abc", "sources": {"finnhub": {"enabled": False}}}}
    source = create_finnhub_source(cfg)
    assert source is None
