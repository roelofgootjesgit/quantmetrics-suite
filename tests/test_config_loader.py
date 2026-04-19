"""Tests for environment overrides in config loader."""

from src.quantbuild.config import load_config, quantbuild_repo_root


def test_quantbuild_repo_root_finds_default_yaml():
    root = quantbuild_repo_root()
    assert (root / "configs" / "default.yaml").is_file()
    assert (root / "src" / "quantbuild" / "config.py").is_file()


def test_news_and_ai_env_overrides(tmp_path, monkeypatch):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(
        "\n".join(
            [
                "news:",
                "  sources:",
                "    newsapi:",
                "      enabled: false",
                "ai:",
                "  openai_api_key: ''",
                "  model: gpt-4o-mini",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("NEWSAPI_KEY", "test-news-key")
    monkeypatch.setenv("NEWSAPI_ENABLED", "true")
    monkeypatch.setenv("NEWSAPI_CATEGORIES", "business, science")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")

    cfg = load_config(str(cfg_file))

    assert cfg["news"]["newsapi_key"] == "test-news-key"
    assert cfg["news"]["sources"]["newsapi"]["enabled"] is True
    assert cfg["news"]["sources"]["newsapi"]["categories"] == ["business", "science"]
    assert cfg["ai"]["openai_api_key"] == "test-openai-key"
    assert cfg["ai"]["model"] == "gpt-4.1-mini"


def test_extends_chain_merges_two_levels(tmp_path):
    """extends -> extends (parent strategy preserved, leaf overrides)."""
    grand = tmp_path / "grand.yaml"
    grand.write_text(
        "strategy:\n  name: sqe_xauusd\n  entry_sweep_disp_fvg_min_count: 2\n",
        encoding="utf-8",
    )
    mid = tmp_path / "mid.yaml"
    mid.write_text(
        "extends: grand.yaml\n"
        "system_mode: EDGE_DISCOVERY\n",
        encoding="utf-8",
    )
    leaf = tmp_path / "leaf.yaml"
    leaf.write_text(
        "extends: mid.yaml\n"
        "backtest:\n"
        "  default_period_days: 30\n",
        encoding="utf-8",
    )
    cfg = load_config(str(leaf))
    assert cfg["strategy"]["name"] == "sqe_xauusd"
    assert cfg["strategy"]["entry_sweep_disp_fvg_min_count"] == 2
    assert cfg["system_mode"] == "EDGE_DISCOVERY"
    assert cfg["backtest"]["default_period_days"] == 30


def test_extends_merges_base_config(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text(
        "strategy:\n  entry_sweep_disp_fvg_min_count: 2\n  liquidity_levels:\n    require_all: false\n",
        encoding="utf-8",
    )
    leaf = tmp_path / "leaf.yaml"
    leaf.write_text(
        "extends: base.yaml\n"
        "backtest:\n"
        "  start_date: '2025-01-01'\n"
        "  end_date: '2025-06-01'\n",
        encoding="utf-8",
    )
    cfg = load_config(str(leaf))
    assert cfg["backtest"]["start_date"] == "2025-01-01"
    assert cfg["backtest"]["end_date"] == "2025-06-01"
    assert cfg["strategy"]["entry_sweep_disp_fvg_min_count"] == 2
    assert cfg["strategy"]["liquidity_levels"]["require_all"] is False


def test_finnhub_env_overrides(tmp_path, monkeypatch):
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(
        "\n".join(
            [
                "news:",
                "  sources:",
                "    finnhub:",
                "      enabled: false",
                "      category: general",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("FINNHUB_API_KEY", "fh-test-key")
    monkeypatch.setenv("FINNHUB_ENABLED", "true")
    monkeypatch.setenv("FINNHUB_CATEGORY", "forex")

    cfg = load_config(str(cfg_file))

    assert cfg["news"]["finnhub_api_key"] == "fh-test-key"
    assert cfg["news"]["sources"]["finnhub"]["enabled"] is True
    assert cfg["news"]["sources"]["finnhub"]["category"] == "forex"
