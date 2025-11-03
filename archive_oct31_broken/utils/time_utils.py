# utils/time_utils.py
from datetime import datetime, timezone

def now_iso_z(timespec: str = "seconds") -> str:
    """
    Return current time in ISO 8601 with Z suffix (UTC), e.g., '2025-10-20T10:45:43Z'.
    timespec: 'seconds'|'milliseconds'|'microseconds'
    """
    return datetime.now(timezone.utc).isoformat(timespec=timespec).replace("+00:00", "Z")
