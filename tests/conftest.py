"""Shared pytest fixtures."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from withings_mcp.withings.client import WithingsClient
from withings_mcp.withings.types import WITHINGS_API_BASE


class MockWithings:
    """Stateful mock of Withings OAuth + API endpoints."""

    def __init__(self) -> None:
        self.refresh_count = 0
        self.api_calls: list[dict[str, Any]] = []
        self.access_token = "access-v1"
        self.refresh_token = "refresh-v1"
        self.reject_access_once = False
        self.force_status: int | None = None
        self.measure_body: dict[str, Any] = {
            "updatetime": 1,
            "timezone": "UTC",
            "measuregrps": [
                {
                    "grpid": 1,
                    "attrib": 0,
                    "date": 1_700_000_000,
                    "created": 1_700_000_000,
                    "category": 1,
                    "measures": [{"value": 72500, "type": 1, "unit": -3}],
                }
            ],
        }
        self.intraday_bodies: list[dict[str, Any]] = []
        self.sleep_summary_body: dict[str, Any] = {
            "series": [{"date": "2024-01-01", "data": {"sleep_score": 80}}]
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        form = dict(httpx.QueryParams(request.content.decode()))

        if url.endswith("/v2/oauth2") and form.get("action") == "requesttoken":
            self.refresh_count += 1
            self.access_token = f"access-v{self.refresh_count + 1}"
            self.refresh_token = f"refresh-v{self.refresh_count + 1}"
            return httpx.Response(
                200,
                json={
                    "status": 0,
                    "body": {
                        "access_token": self.access_token,
                        "refresh_token": self.refresh_token,
                        "expires_in": 10800,
                        "userid": 12345,
                        "scope": "user.info,user.metrics,user.activity,user.sleepevents",
                    },
                },
            )

        auth = request.headers.get("Authorization", "")
        self.api_calls.append({"url": url, "form": form, "auth": auth})

        if self.force_status is not None:
            status = self.force_status
            self.force_status = None
            return httpx.Response(200, json={"status": status, "error": f"forced {status}"})

        if self.reject_access_once and auth == "Bearer access-v1":
            self.reject_access_once = False
            return httpx.Response(
                200,
                json={"status": 343, "error": "Invalid token"},
            )

        action = form.get("action")
        if action == "getmeas":
            return httpx.Response(200, json={"status": 0, "body": self.measure_body})
        if action == "getintradayactivity":
            if self.intraday_bodies:
                body = self.intraday_bodies.pop(0)
            else:
                body = {
                    "series": {
                        str(form.get("startdate", "0")): {"heart_rate": 70},
                    }
                }
            return httpx.Response(200, json={"status": 0, "body": body})
        if action == "getsummary":
            return httpx.Response(200, json={"status": 0, "body": self.sleep_summary_body})

        return httpx.Response(200, json={"status": 0, "body": {}})


@pytest.fixture
def mock_api() -> MockWithings:
    return MockWithings()


@pytest.fixture
def http_client(mock_api: MockWithings) -> httpx.Client:
    transport = httpx.MockTransport(mock_api.handler)
    return httpx.Client(transport=transport, base_url=WITHINGS_API_BASE)


@pytest.fixture
def token_file(tmp_path) -> str:
    path = tmp_path / "tokens.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "access-v1",
                "refresh_token": "refresh-v1",
                "expires_at": 9_999_999_999,
                "expires_in": 10800,
                "userid": 12345,
            }
        ),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def client(http_client: httpx.Client, token_file: str) -> WithingsClient:
    return WithingsClient(
        client_id="cid",
        client_secret="csecret",
        refresh_token="refresh-v1",
        token_file=token_file,
        http_client=http_client,
    )
