import re
from datetime import datetime, timezone


def now_iso_ms() -> str:
    """ISO 8601 UTC à la milliseconde, terminé par Z (ex. 2026-11-07T10:00:00.123Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def iso_s(dt: datetime) -> str:
    """ISO 8601 UTC à la seconde (format des _id de stats_buckets)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_UNITS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(s: str) -> int:
    """'10s' -> 10, '15m' -> 900, '1h' -> 3600."""
    m = re.fullmatch(r"(\d+)\s*([smh])", s.strip().lower())
    if not m:
        raise ValueError(f"durée invalide : {s!r} (attendu ex. 10s, 15m, 1h)")
    return int(m.group(1)) * _UNITS[m.group(2)]
