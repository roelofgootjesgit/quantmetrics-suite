"""
Trading session logic: London, NY, Overlap = entries; Asia = range-only.
Supports killzone (strict ICT) and extended (continuous 07-16 UTC) modes.
"""

SESSION_LONDON = "London"
SESSION_NY = "New York"
SESSION_OVERLAP = "Overlap"
SESSION_ASIA = "Asia"

ENTRY_SESSIONS = (SESSION_LONDON, SESSION_NY, SESSION_OVERLAP)
RANGE_ONLY_SESSIONS = (SESSION_ASIA,)

SESSION_MODE = "killzone"


def session_from_timestamp(ts, mode: str | None = None) -> str:
    """Determine session from timestamp (assumes UTC)."""
    if hasattr(ts, "to_pydatetime"):
        ts = ts.to_pydatetime()
    h = getattr(ts, "hour", 0)
    _mode = mode or SESSION_MODE

    if _mode == "extended":
        if 7 <= h < 10:
            return SESSION_LONDON
        if 10 <= h < 12:
            return SESSION_OVERLAP
        if 12 <= h < 16:
            return SESSION_NY
        return SESSION_ASIA
    else:
        if 7 <= h < 10:
            return SESSION_LONDON
        if 12 <= h < 15:
            return SESSION_NY
        return SESSION_ASIA
