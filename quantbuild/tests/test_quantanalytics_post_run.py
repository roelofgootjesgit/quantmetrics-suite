"""QuantBuild → QuantAnalytics post-run helpers."""

from __future__ import annotations

from pathlib import Path

from src.quantbuild.integration.quantanalytics_post_run import discover_quantanalytics_output_rapport


def test_discover_quantanalytics_output_rapport_sibling(tmp_path: Path) -> None:
    ws = tmp_path / "workspace"
    qb = ws / "quantbuild"
    qa = ws / "quantanalytics"
    (qa / "quantmetrics_analytics").mkdir(parents=True)
    (qa / "pyproject.toml").write_text('name = "quantmetrics-analytics"\n', encoding="utf-8")
    (qa / "output_rapport").mkdir(parents=True)

    got = discover_quantanalytics_output_rapport(quantbuild_root=qb)
    assert got is not None
    assert got.resolve() == (qa / "output_rapport").resolve()


def test_discover_quantanalytics_output_rapport_missing(tmp_path: Path) -> None:
    qb = tmp_path / "solo" / "quantbuild"
    qb.mkdir(parents=True)
    assert discover_quantanalytics_output_rapport(quantbuild_root=qb) is None
