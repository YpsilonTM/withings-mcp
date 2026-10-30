"""JSON-line logging to stderr (stdout is reserved for MCP JSON-RPC)."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from typing import Any, Literal

LogLevel = Literal["error", "warn", "info", "debug"]

_LEVEL_ORDER: dict[LogLevel, int] = {
    "error": 0,
    "warn": 1,
    "info": 2,
    "debug": 3,
}

_SECRET_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "client_secret",
        "authorization",
        "code",
    }
)


def _parse_level(raw: str | None) -> LogLevel:
    v = (raw or "info").lower()
    if v in ("error", "warn", "info", "debug"):
        return v  # type: ignore[return-value]
    return "info"


_current_level: LogLevel = _parse_level(os.environ.get("WITHINGS_LOG_LEVEL"))


def set_log_level(level: LogLevel) -> None:
    global _current_level
    _current_level = level


def get_log_level() -> LogLevel:
    return _current_level


def _sanitize(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        lower = key.lower()
        is_secret = (
            lower in _SECRET_KEYS
            or lower.endswith("_token")
            or lower == "token"
            or lower.endswith("_secret")
            or lower == "secret"
            or lower == "authorization"
            or lower == "code"
        )
        is_meta = (
            lower.endswith("configured")
            or lower == "tokenfile"
            or lower == "token_file"
            or lower == "writepath"
        )
        if is_secret and not is_meta:
            out[key] = False if value is None or value == "" else "[redacted]"
            continue
        out[key] = value
    return out


def _write(level: LogLevel, msg: str, fields: dict[str, Any] | None = None) -> None:
    if _LEVEL_ORDER[level] > _LEVEL_ORDER[_current_level]:
        return
    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "level": level,
        "msg": msg,
        **_sanitize(fields or {}),
    }
    sys.stderr.write(json.dumps(entry, default=str) + "\n")
    sys.stderr.flush()


class _Log:
    def error(self, msg: str, fields: dict[str, Any] | None = None) -> None:
        _write("error", msg, fields)

    def warn(self, msg: str, fields: dict[str, Any] | None = None) -> None:
        _write("warn", msg, fields)

    def info(self, msg: str, fields: dict[str, Any] | None = None) -> None:
        _write("info", msg, fields)

    def debug(self, msg: str, fields: dict[str, Any] | None = None) -> None:
        _write("debug", msg, fields)


log = _Log()
