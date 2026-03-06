# utils/time_utils.py
from datetime import datetime, timezone

def now_iso_z(timespec: str = "seconds") -> str:
    """
    Return current local time in ISO 8601, e.g., '2025-10-20T10:45:43'.
    timespec: 'seconds'|'milliseconds'|'microseconds'
    """
    return datetime.now().isoformat(timespec=timespec)
