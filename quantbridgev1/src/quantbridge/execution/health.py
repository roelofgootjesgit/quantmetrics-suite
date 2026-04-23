from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

HealthStatus = Literal["healthy", "degraded", "unhealthy"]
SessionState = Literal["connected", "disconnected", "expired", "unknown"]


@dataclass(frozen=True)
class HealthReport:
    status: HealthStatus
    session_state: SessionState
    last_error: Optional[str] = None
    last_success_at: Optional[datetime] = None
