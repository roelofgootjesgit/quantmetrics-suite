from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BrokerError(Exception):
    code: str
    message: str
    retryable: bool = False
    raw: Optional[dict] = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def classify_error(message: str) -> str:
    msg = (message or "").lower()
    if "auth" in msg or "unauthorized" in msg or "token" in msg:
        return "auth_failed"
    if "session" in msg and ("expired" in msg or "invalid" in msg):
        return "session_expired"
    if "symbol" in msg or "instrument" in msg:
        return "invalid_symbol"
    if "margin" in msg or "insufficient" in msg:
        return "insufficient_margin"
    if "timeout" in msg or "timed out" in msg:
        return "network_timeout"
    if "rate" in msg and "limit" in msg:
        return "rate_limited"
    if "reject" in msg or "cancel" in msg:
        return "order_rejected"
    return "unknown_broker_error"
