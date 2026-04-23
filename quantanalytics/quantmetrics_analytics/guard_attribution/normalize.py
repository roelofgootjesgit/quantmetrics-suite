"""Lightweight string normalization for slice keys."""

from __future__ import annotations


def norm_key(val: object) -> str:
    s = str(val or "").strip().lower()
    return s if s else "unknown"
