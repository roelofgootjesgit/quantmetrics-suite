"""Tests for Telegram alert formatting behavior."""

from src.quantbuild.alerts.telegram import TelegramAlerter


def _cfg():
    return {
        "monitoring": {
            "telegram": {
                "enabled": True,
                "bot_token": "x",
                "chat_id": "y",
                "alerts": {"news_event": True},
            }
        }
    }


def test_news_event_alert_uses_impact_label(monkeypatch):
    alerter = TelegramAlerter(_cfg())
    captured = {}

    def fake_send(text: str, parse_mode: str = "HTML") -> bool:
        captured["text"] = text
        captured["parse_mode"] = parse_mode
        return True

    monkeypatch.setattr(alerter, "_send", fake_send)
    ok = alerter.alert_news_event(
        headline="Fed surprises market with hawkish hold",
        source="Reuters",
        sentiment="bearish",
        impact=-0.81,
        classification="macro/macro_rates",
    )
    assert ok
    assert "NEWS IMPACT" in captured["text"]
    assert "HIGH" in captured["text"]
    assert "macro/macro_rates" in captured["text"]
