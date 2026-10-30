"""Token refresh, atomic persistence, and 343-retry tests."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from withings_mcp.withings.client import (
    WithingsAuthError,
    WithingsClient,
    WithingsRateLimitError,
)


def test_refresh_persists_tokens_atomically(
    client: WithingsClient,
    mock_api,
    token_file: str,
) -> None:
    # Expire access token so ensure_access_token refreshes
    client.tokens["expires_at"] = 1
    client.tokens["access_token"] = "access-v1"

    token = client.ensure_access_token()
    assert token == "access-v2"
    assert mock_api.refresh_count == 1
    assert client.tokens["refresh_token"] == "refresh-v2"

    on_disk = json.loads(Path(token_file).read_text(encoding="utf-8"))
    assert on_disk["access_token"] == "access-v2"
    assert on_disk["refresh_token"] == "refresh-v2"
    assert "expires_at" in on_disk

    # No leftover temp files
    leftovers = list(Path(token_file).parent.glob(".tokens.*.tmp"))
    assert leftovers == []


def test_status_343_refreshes_once_then_succeeds(
    client: WithingsClient,
    mock_api,
    token_file: str,
) -> None:
    mock_api.reject_access_once = True
    body = client.request(
        "/measure",
        {"action": "getmeas", "startdate": 1, "enddate": 2},
    )
    assert body["measuregrps"]
    assert mock_api.refresh_count == 1
    on_disk = json.loads(Path(token_file).read_text(encoding="utf-8"))
    assert on_disk["refresh_token"] == "refresh-v2"


def test_status_343_after_refresh_raises_auth_error(
    http_client: httpx.Client,
    token_file: str,
    mock_api,
) -> None:
    # Always return 343 from API; refresh still succeeds once
    def always_343(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/v2/oauth2"):
            mock_api.refresh_count += 1
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "body": {
                        "access_token": f"access-v{mock_api.refresh_count + 1}",
                        "refresh_token": f"refresh-v{mock_api.refresh_count + 1}",
                        "expires_in": 10800,
                    },
                },
            )
        return httpx.Response(200, json={"status": 343, "error": "Invalid token"})

    transport = httpx.MockTransport(always_343)
    http = httpx.Client(transport=transport)
    c = WithingsClient(
        client_id="cid",
        client_secret="csecret",
        refresh_token="refresh-v1",
        token_file=token_file,
        http_client=http,
    )
    c.tokens["access_token"] = "stale"
    c.tokens["expires_at"] = 9_999_999_999

    with pytest.raises(WithingsAuthError, match="withings-mcp auth"):
        c.request("/measure", {"action": "getmeas", "startdate": 1, "enddate": 2})


def test_status_601_is_rate_limit(client: WithingsClient, mock_api) -> None:
    mock_api.force_status = 601
    with pytest.raises(WithingsRateLimitError, match="601"):
        client.request("/measure", {"action": "getmeas", "startdate": 1, "enddate": 2})


def test_status_100_is_ok_empty(client: WithingsClient, mock_api) -> None:
    mock_api.force_status = 100
    # force_status returns error body without body key — client returns {}
    result = client.request("/measure", {"action": "getmeas", "startdate": 1, "enddate": 2})
    assert result == {}
