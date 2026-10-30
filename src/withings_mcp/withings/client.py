"""Withings API client with token refresh and atomic persistence."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from withings_mcp.auth.oauth import refresh_access_token
from withings_mcp.log import log
from withings_mcp.withings.types import WITHINGS_API_BASE, TokenSet

AUTH_ERROR_HINT = "Re-run `withings-mcp auth` and update WITHINGS_REFRESH_TOKEN / token file."


class WithingsApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class WithingsAuthError(WithingsApiError):
    """Invalid/expired tokens; user must re-authorize."""


class WithingsRateLimitError(WithingsApiError):
    """Withings status 601 — rate limited."""


class WithingsClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        token_file: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file
        self._http = http_client or httpx.Client()
        self._owns_http = http_client is None
        self._lock = threading.Lock()

        from_file = load_token_file(token_file) if token_file else None
        self.tokens: TokenSet = {
            "access_token": (from_file or {}).get("access_token") or "",
            "refresh_token": (from_file or {}).get("refresh_token") or refresh_token,
        }
        if from_file:
            for key in ("userid", "expires_in", "expires_at", "scope"):
                if key in from_file:
                    self.tokens[key] = from_file[key]  # type: ignore[literal-required]

        if not self.tokens.get("refresh_token"):
            raise WithingsAuthError(
                "Missing refresh token. Set WITHINGS_REFRESH_TOKEN or provide a token file "
                f"from `withings-mcp auth`. {AUTH_ERROR_HINT}"
            )

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def ensure_access_token(self) -> str:
        now = int(time.time())
        skew = 60
        access = self.tokens.get("access_token") or ""
        expires_at = self.tokens.get("expires_at")
        if access and expires_at and expires_at > now + skew:
            return access

        with self._lock:
            access = self.tokens.get("access_token") or ""
            expires_at = self.tokens.get("expires_at")
            if access and expires_at and expires_at > now + skew:
                return access
            self._do_refresh()
            return self.tokens["access_token"]

    def _do_refresh(self) -> None:
        next_tokens = refresh_access_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=self.tokens["refresh_token"],
            http_client=self._http,
        )
        self.tokens = next_tokens
        self.persist_tokens()

    def persist_tokens(self) -> None:
        """Atomically write the current token set to WITHINGS_TOKEN_FILE."""
        if not self.token_file:
            log.debug("No TOKEN_FILE configured; rotated refresh token kept in memory only")
            return
        path = Path(self.token_file)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.tokens, indent=2) + "\n"
            fd, tmp_name = tempfile.mkstemp(
                dir=str(path.parent),
                prefix=".tokens.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(tmp_name, 0o600)
                os.replace(tmp_name, path)
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
                raise
            log.info("Persisted rotated tokens to TOKEN_FILE", {"tokenFile": self.token_file})
        except Exception as e:
            log.warn(
                "Failed to persist token file; refresh token may be lost on restart",
                {"tokenFile": self.token_file, "error": str(e)},
            )

    def request(
        self,
        path: str,
        params: dict[str, str | int | float | None],
    ) -> Any:
        action = str(params.get("action") or "")
        started = time.monotonic()

        def do_call(access_token: str) -> tuple[int, dict[str, Any]]:
            body: dict[str, str] = {}
            for k, v in params.items():
                if v is None or v == "":
                    continue
                body[k] = str(v)

            log.debug(
                "Withings API request",
                {"path": path, "action": action, "params": _summarize_params(params)},
            )
            res = self._http.post(
                f"{WITHINGS_API_BASE}{path}",
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            return res.status_code, res.json()

        access_token = self.ensure_access_token()
        http_status, json_data = do_call(access_token)

        # 343 = invalid/expired access token — refresh once and retry
        if json_data.get("status") == 343:
            log.warn(
                "Access token rejected (343); refreshing and retrying",
                {"path": path, "action": action},
            )
            try:
                with self._lock:
                    self._do_refresh()
                access_token = self.tokens["access_token"]
            except Exception as e:
                raise WithingsAuthError(
                    f"Withings token refresh failed after status=343: {e}. {AUTH_ERROR_HINT}",
                    status=343,
                ) from e
            http_status, json_data = do_call(access_token)
            if json_data.get("status") == 343:
                raise WithingsAuthError(
                    f"Withings API still returned status=343 after refresh "
                    f"(path={path} action={action}). {AUTH_ERROR_HINT}",
                    status=343,
                )

        duration_ms = int((time.monotonic() - started) * 1000)
        status = json_data.get("status")

        if status == 601:
            log.error(
                "Withings API rate limited",
                {
                    "path": path,
                    "action": action,
                    "status": status,
                    "error": json_data.get("error"),
                    "httpStatus": http_status,
                    "durationMs": duration_ms,
                },
            )
            raise WithingsRateLimitError(
                f"Withings rate limit (status=601) path={path} action={action}: "
                f"{json_data.get('error') or 'too many requests'}. Back off and retry later.",
                status=601,
            )

        if status not in (0, 100):
            log.error(
                "Withings API error",
                {
                    "path": path,
                    "action": action,
                    "status": status,
                    "error": json_data.get("error"),
                    "httpStatus": http_status,
                    "durationMs": duration_ms,
                },
            )
            raise WithingsApiError(
                f"Withings API error path={path} action={action} status={status}: "
                f"{json_data.get('error') or 'unknown'}",
                status=status if isinstance(status, int) else None,
            )

        log.info(
            "Withings API ok",
            {
                "path": path,
                "action": action,
                "status": status,
                "durationMs": duration_ms,
                "empty": status == 100,
            },
        )
        body = json_data.get("body")
        if isinstance(body, dict):
            log.debug(
                "Withings API response meta",
                {
                    "path": path,
                    "action": action,
                    "more": body.get("more"),
                    "offset": body.get("offset"),
                },
            )
        return body if body is not None else {}


def load_token_file(path: str) -> TokenSet | None:
    try:
        p = Path(path)
        if not p.exists():
            return None
        parsed = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict) or not parsed.get("refresh_token"):
            return None
        log.info("Loaded tokens from TOKEN_FILE", {"tokenFile": path})
        return parsed  # type: ignore[return-value]
    except Exception as e:
        log.warn(
            "Could not read TOKEN_FILE",
            {"tokenFile": path, "error": str(e)},
        )
        return None


def _summarize_params(
    params: dict[str, str | int | float | None],
) -> dict[str, str | int | float]:
    out: dict[str, str | int | float] = {}
    for k, v in params.items():
        if v is None or v == "":
            continue
        out[k] = v
    return out


def require_env(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


def create_client_from_env(*, http_client: httpx.Client | None = None) -> WithingsClient:
    client_id = require_env("WITHINGS_CLIENT_ID")
    client_secret = require_env("WITHINGS_CLIENT_SECRET")
    refresh_token = (os.environ.get("WITHINGS_REFRESH_TOKEN") or "").strip()
    token_file = (os.environ.get("WITHINGS_TOKEN_FILE") or "").strip() or (
        "/data/tokens.json" if Path("/data").exists() else None
    )

    log.info(
        "Creating Withings client",
        {
            "clientIdConfigured": bool(client_id),
            "clientSecretConfigured": bool(client_secret),
            "refreshTokenConfigured": bool(refresh_token) or bool(token_file),
            "tokenFileConfigured": bool(token_file),
            "tokenFile": token_file,
        },
    )

    return WithingsClient(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token,
        token_file=token_file,
        http_client=http_client,
    )
