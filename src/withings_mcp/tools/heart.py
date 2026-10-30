"""Heart / ECG tools."""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from withings_mcp.log import log
from withings_mcp.tools.helpers import resolve_unix_range
from withings_mcp.withings.client import WithingsClient


def register_heart_tools(mcp: FastMCP, client: WithingsClient) -> None:
    @mcp.tool(
        name="withings_list_heart_records",
        description=(
            "List ECG / heart recordings (Heart v2 list), including AFib classification metadata. "
            "Requires an ECG-capable device (e.g. ScanWatch ECG / BeamO). Often empty if the user "
            "only has a scale + non-ECG tracker. Default range: last 30 days. Use "
            "withings_get_heart_rate with include_intraday for continuous watch HR instead."
        ),
    )
    def withings_list_heart_records(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 30 days ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[int | None, "Pagination offset."] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start, end = resolve_unix_range(
                startdate=startdate, enddate=enddate, default_hours=24 * 30
            )
            log.info(
                "Tool call",
                {
                    "tool": "withings_list_heart_records",
                    "startdate": start,
                    "enddate": end,
                    "offset": offset,
                },
            )
            body = client.request(
                "/v2/heart",
                {
                    "action": "list",
                    "startdate": start,
                    "enddate": end,
                    "offset": offset,
                },
            )
            series = (body or {}).get("series") if isinstance(body, dict) else None
            log.info(
                "Tool done",
                {
                    "tool": "withings_list_heart_records",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "count": len(series) if isinstance(series, list) else None,
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error(
                "Tool failed",
                {"tool": "withings_list_heart_records", "error": str(e)},
            )
            raise ToolError(str(e)) from e

    @mcp.tool(
        name="withings_get_heart_ecg",
        description=(
            "Fetch a single ECG waveform/signal by signalid from withings_list_heart_records. "
            "Only useful when withings_list_heart_records returned recordings (ECG-capable "
            "device). Not for continuous watch heart rate."
        ),
    )
    def withings_get_heart_ecg(
        signalid: Annotated[
            str | int,
            "ECG signal id returned by withings_list_heart_records.",
        ],
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            log.info(
                "Tool call",
                {"tool": "withings_get_heart_ecg", "signalid": str(signalid)},
            )
            body = client.request(
                "/v2/heart",
                {"action": "get", "signalid": signalid},
            )
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_heart_ecg",
                    "durationMs": int((time.monotonic() - started) * 1000),
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error("Tool failed", {"tool": "withings_get_heart_ecg", "error": str(e)})
            raise ToolError(str(e)) from e
