"""Tests for QuantLog repository path resolution."""

from pathlib import Path

from src.quantbuild.quantlog_repo import resolve_quantlog_repo_path


def _fake_repo(root: Path) -> Path:
    (root / "src" / "quantlog").mkdir(parents=True)
    return root


def test_resolve_accepts_quantlog_root(tmp_path, monkeypatch):
    good = _fake_repo(tmp_path / "ql")
    monkeypatch.delenv("QUANTLOG_REPO_PATH", raising=False)
    monkeypatch.setenv("QUANTLOG_ROOT", str(good))
    assert resolve_quantlog_repo_path() == good.resolve()


def test_resolve_prefers_repo_path_over_root(tmp_path, monkeypatch):
    preferred = _fake_repo(tmp_path / "a")
    other = _fake_repo(tmp_path / "b")
    monkeypatch.setenv("QUANTLOG_REPO_PATH", str(preferred))
    monkeypatch.setenv("QUANTLOG_ROOT", str(other))
    assert resolve_quantlog_repo_path() == preferred.resolve()


def test_resolve_falls_back_to_root_when_repo_path_invalid(tmp_path, monkeypatch):
    fallback = _fake_repo(tmp_path / "ok")
    monkeypatch.setenv("QUANTLOG_REPO_PATH", str(tmp_path / "missing"))
    monkeypatch.setenv("QUANTLOG_ROOT", str(fallback))
    assert resolve_quantlog_repo_path() == fallback.resolve()
