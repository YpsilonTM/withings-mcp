"""Withings OAuth2 authorize / exchange / refresh (ported from TypeScript)."""

from __future__ import annotations

import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from withings_mcp.log import log
from withings_mcp.withings.types import (
    DEFAULT_SCOPES,
    WITHINGS_API_BASE,
    WITHINGS_AUTH_URL,
    TokenSet,
)


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    scopes: str,
    state: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
    }
    return f"{WITHINGS_AUTH_URL}?{urlencode(params)}"


def exchange_authorization_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    http_client: httpx.Client | None = None,
) -> TokenSet:
    body = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    log.info("Exchanging authorization code for tokens")
    client = http_client or httpx.Client()
    owns = http_client is None
    try:
        res = client.post(
            f"{WITHINGS_API_BASE}/v2/oauth2",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        json_data: dict[str, Any] = res.json()
    finally:
        if owns:
            client.close()

    status = json_data.get("status")
    token_body = json_data.get("body") or {}
    if status != 0 or not token_body.get("access_token") or not token_body.get("refresh_token"):
        log.error(
            "Token exchange failed",
            {"status": status, "error": json_data.get("error"), "httpStatus": res.status_code},
        )
        err = json_data.get("error") or "unknown"
        raise RuntimeError(f"Withings token exchange failed (status={status}): {err}")

    tokens: TokenSet = {
        **token_body,
        "expires_at": int(time.time()) + int(token_body.get("expires_in") or 10800),
    }
    userid = tokens.get("userid")
    log.info(
        "Token exchange succeeded",
        {
            "status": status,
            "userid": str(userid)[-4:] if userid is not None else None,
            "expires_in": tokens.get("expires_in"),
            "scope": tokens.get("scope"),
        },
    )
    return tokens


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    http_client: httpx.Client | None = None,
) -> TokenSet:
    body = {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    log.info("Refreshing access token")
    client = http_client or httpx.Client()
    owns = http_client is None
    try:
        res = client.post(
            f"{WITHINGS_API_BASE}/v2/oauth2",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        json_data: dict[str, Any] = res.json()
    finally:
        if owns:
            client.close()

    status = json_data.get("status")
    token_body = json_data.get("body") or {}
    if status != 0 or not token_body.get("access_token") or not token_body.get("refresh_token"):
        log.error(
            "Token refresh failed",
            {"status": status, "error": json_data.get("error"), "httpStatus": res.status_code},
        )
        err = json_data.get("error") or "unknown"
        raise RuntimeError(
            f"Withings token refresh failed (status={status}): {err}. "
            "Re-run `withings-mcp auth` and update WITHINGS_REFRESH_TOKEN / token file."
        )

    tokens: TokenSet = {
        **token_body,
        "expires_at": int(time.time()) + int(token_body.get("expires_in") or 10800),
    }
    userid = tokens.get("userid")
    log.info(
        "Token refresh succeeded",
        {
            "status": status,
            "userid": str(userid)[-4:] if userid is not None else None,
            "expires_in": tokens.get("expires_in"),
        },
    )
    return tokens


def run_oauth_flow(
    *,
    client_id: str,
    client_secret: str,
    redirect_port: int | None = None,
    scopes: str | None = None,
    http_client: httpx.Client | None = None,
) -> TokenSet:
    """Interactive OAuth: local callback server, print authorize URL, wait for code."""
    import os
    import sys

    port = (
        redirect_port
        if redirect_port is not None
        else int(os.environ.get("WITHINGS_REDIRECT_PORT") or 8765)
    )
    redirect_uri = f"http://localhost:{port}/callback"
    scope_str = scopes or DEFAULT_SCOPES
    state = secrets.token_hex(16)
    authorize_url = build_authorize_url(client_id, redirect_uri, scope_str, state)

    log.info("Starting OAuth callback server", {"port": port, "redirectUri": redirect_uri})

    result: dict[str, str | None] = {"code": None, "error": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            # Suppress default HTTP access logs (would go to stderr as plain text)
            return

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Not found")
                    return

                qs = parse_qs(parsed.query)
                err = (qs.get("error") or [None])[0]
                if err:
                    log.error("OAuth callback error", {"error": err})
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"<h1>Authorization failed</h1><p>{err}</p>".encode())
                    result["error"] = f"OAuth error: {err}"
                    return

                returned_state = (qs.get("state") or [None])[0]
                if returned_state != state:
                    log.error("OAuth state mismatch")
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>Invalid state</h1>")
                    result["error"] = "OAuth state mismatch"
                    return

                auth_code = (qs.get("code") or [None])[0]
                if not auth_code:
                    log.error("OAuth callback missing code")
                    self.send_response(400)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>Missing code</h1>")
                    result["error"] = "Missing authorization code"
                    return

                log.info("OAuth callback received")
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Authorization successful</h1>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                )
                result["code"] = auth_code
            except Exception as e:
                log.error(
                    "OAuth callback handler error",
                    {"error": str(e)},
                )
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Internal error")
                result["error"] = str(e)

    server = HTTPServer(("0.0.0.0", port), Handler)
    log.info("Open this URL in your browser to authorize", {"authorizeUrl": authorize_url})
    sys.stderr.write(f"\nAuthorize Withings access:\n{authorize_url}\n\n")
    sys.stderr.flush()

    try:
        while result["code"] is None and result["error"] is None:
            server.handle_request()
    finally:
        server.server_close()

    if result["error"]:
        raise RuntimeError(result["error"])
    assert result["code"] is not None

    return exchange_authorization_code(
        client_id=client_id,
        client_secret=client_secret,
        code=result["code"],
        redirect_uri=redirect_uri,
        http_client=http_client,
    )
