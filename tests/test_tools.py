"""Tool wrapper tests (measurements, intraday activity, sleep summary)."""

from __future__ import annotations

from withings_mcp.tools.activity import fetch_intraday_activity
from withings_mcp.tools.helpers import iter_unix_windows
from withings_mcp.tools.measures import get_meas
from withings_mcp.withings.client import WithingsClient


def test_get_measurements_decodes_weight(client: WithingsClient) -> None:
    data = get_meas(client, [1], startdate=1, enddate=2)
    assert data["count"] == 1
    grp = data["measuregrps"][0]
    assert grp["measures"][0]["name"] == "Weight"
    assert grp["measures"][0]["value"] == 72.5
    assert grp["measures"][0]["unit"] == "kg"
    assert "date_iso" in grp


def test_intraday_activity_splits_over_24h(client: WithingsClient, mock_api) -> None:
    start = 1_700_000_000
    end = start + (36 * 3600)  # 36 hours → 2 windows
    windows = iter_unix_windows(start, end, max_span=24 * 3600)
    assert len(windows) == 2

    mock_api.intraday_bodies = [
        {"series": {"100": {"heart_rate": 60}}},
        {"series": {"200": {"heart_rate": 70}}},
    ]
    body = fetch_intraday_activity(client, start, end, "heart_rate")
    assert body["series"] == {"100": {"heart_rate": 60}, "200": {"heart_rate": 70}}
    assert len(body["windows"]) == 2
    assert len(mock_api.api_calls) >= 2
    actions = [c["form"].get("action") for c in mock_api.api_calls]
    assert actions.count("getintradayactivity") == 2


def test_sleep_summary_default_fields(client: WithingsClient, mock_api) -> None:
    body = client.request(
        "/v2/sleep",
        {
            "action": "getsummary",
            "startdateymd": "2024-01-01",
            "enddateymd": "2024-01-07",
            "data_fields": "sleep_score",
        },
    )
    assert body["series"][0]["data"]["sleep_score"] == 80
    call = mock_api.api_calls[-1]
    assert call["form"]["action"] == "getsummary"
    assert call["form"]["startdateymd"] == "2024-01-01"
