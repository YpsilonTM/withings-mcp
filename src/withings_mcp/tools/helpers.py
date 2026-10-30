"""Shared date helpers (ported from TypeScript)."""

from __future__ import annotations

import time
from datetime import UTC, datetime


def now_unix() -> int:
    return int(time.time())


def hours_ago_unix(hours: float) -> int:
    return now_unix() - int(hours * 3600)


def days_ago_unix(days: float) -> int:
    return now_unix() - int(days * 86400)


def to_ymd(unix: int) -> str:
    return datetime.fromtimestamp(unix, tz=UTC).strftime("%Y-%m-%d")


def resolve_unix_range(
    *,
    startdate: int | None = None,
    enddate: int | None = None,
    default_hours: float = 24,
) -> tuple[int, int]:
    end = enddate if enddate is not None else now_unix()
    start = startdate if startdate is not None else end - int(default_hours * 3600)
    if start > end:
        raise ValueError("startdate must be <= enddate")
    return start, end


def resolve_ymd_range(
    *,
    startdateymd: str | None = None,
    enddateymd: str | None = None,
    default_days: int = 7,
) -> tuple[str, str]:
    end = enddateymd if enddateymd is not None else to_ymd(now_unix())
    start = startdateymd if startdateymd is not None else to_ymd(days_ago_unix(default_days - 1))
    return start, end


def iter_unix_windows(
    startdate: int,
    enddate: int,
    *,
    max_span: int = 24 * 3600,
) -> list[tuple[int, int]]:
    """Split [startdate, enddate] into contiguous windows of at most max_span seconds."""
    if startdate > enddate:
        raise ValueError("startdate must be <= enddate")
    windows: list[tuple[int, int]] = []
    cursor = startdate
    while cursor < enddate:
        chunk_end = min(cursor + max_span, enddate)
        windows.append((cursor, chunk_end))
        cursor = chunk_end
    if not windows:
        windows.append((startdate, enddate))
    return windows
