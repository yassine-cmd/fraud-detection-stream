"""Utilitaires de temps et de parsing partagés par l'API."""
import re
from datetime import datetime, timezone
from typing import Any, Optional


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso_ms() -> str:
    """ISO 8601 UTC à la milliseconde, terminé par Z (ex. 2026-11-07T10:00:00.123Z)."""
    return now_utc().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_s(dt: datetime) -> str:
    """ISO 8601 UTC à la seconde (ex. 2026-11-07T10:00:00Z)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_ms(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value: Any) -> Optional[datetime]:
    """Parse une date ISO (Z accepté) ou retourne None."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def timestamp_to_iso(value: Any) -> str:
    """Convertit datetime / chaîne ISO en ISO 8601 UTC avec suffixe Z."""
    if isinstance(value, datetime):
        return iso_ms(value)
    parsed = parse_iso(value)
    return iso_ms(parsed) if parsed else (str(value) if value is not None else "")


_UNITS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(s: str) -> int:
    """'10s' -> 10, '15m' -> 900, '1h' -> 3600."""
    m = re.fullmatch(r"(\d+)\s*([smh])", str(s).strip().lower())
    if not m:
        raise ValueError(f"durée invalide : {s!r} (attendu ex. 10s, 15m, 1h)")
    return int(m.group(1)) * _UNITS[m.group(2)]
