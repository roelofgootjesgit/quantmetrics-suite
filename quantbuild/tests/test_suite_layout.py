from __future__ import annotations

from pathlib import Path

from src.quantbuild.suite_layout import SuiteLayoutError, validate_suite_layout


def _mk_suite(tmp_path: Path) -> Path:
    suite_root = tmp_path / "quantmetrics-suite"
    for name in ("quantbuild", "quantbridge", "quantlog", "quantanalytics", "quantmetrics_os"):
        (suite_root / name).mkdir(parents=True, exist_ok=True)
    (suite_root / "quantbridge" / "src").mkdir(parents=True, exist_ok=True)
    (suite_root / "quantlog" / "src" / "quantlog").mkdir(parents=True, exist_ok=True)
    return suite_root


def test_validate_suite_layout_success(tmp_path, monkeypatch):
    suite_root = _mk_suite(tmp_path)
    monkeypatch.setattr("src.quantbuild.suite_layout.quantbuild_repo_root", lambda: suite_root / "quantbuild")
    monkeypatch.delenv("QUANTLOG_ROOT", raising=False)
    monkeypatch.setenv("QUANTMETRICS_OS_ROOT", str(suite_root / "quantmetrics_os"))
    monkeypatch.setenv("QUANTLOG_REPO_PATH", str(suite_root / "quantlog"))
    monkeypatch.setenv("QUANTBRIDGE_SRC_PATH", str(suite_root / "quantbridge" / "src"))
    monkeypatch.setenv(
        "QUANTMETRICS_ANALYTICS_OUTPUT_DIR",
        str(suite_root / "quantanalytics" / "output_rapport"),
    )
    report = validate_suite_layout()
    assert report["suite_root"].lower().endswith("quantmetrics-suite")


def test_validate_suite_layout_rejects_mismatched_quantbridge_path(tmp_path, monkeypatch):
    suite_root = _mk_suite(tmp_path)
    monkeypatch.setattr("src.quantbuild.suite_layout.quantbuild_repo_root", lambda: suite_root / "quantbuild")
    monkeypatch.delenv("QUANTLOG_ROOT", raising=False)
    monkeypatch.setenv("QUANTLOG_REPO_PATH", str(suite_root / "quantlog"))
    monkeypatch.setenv("QUANTMETRICS_OS_ROOT", str(suite_root / "quantmetrics_os"))
    monkeypatch.setenv("QUANTBRIDGE_SRC_PATH", str(suite_root / ("quantbridge" + "v1") / "src"))
    try:
        validate_suite_layout()
    except SuiteLayoutError as exc:
        assert "QUANTBRIDGE_SRC_PATH mismatch" in str(exc)
    else:
        raise AssertionError("Expected SuiteLayoutError")
