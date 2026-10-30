"""User device and goals tools."""

from __future__ import annotations

import time
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from withings_mcp.log import log
from withings_mcp.withings.client import WithingsClient


def register_user_tools(mcp: FastMCP, client: WithingsClient) -> None:
    @mcp.tool(
        name="withings_list_devices",
        description=(
            "List Withings devices paired to the authorized account (e.g. Scale, Activity "
            "Tracker, Sleep Monitor). Useful to see which data sources exist before querying."
        ),
    )
    def withings_list_devices() -> dict[str, Any]:
        started = time.monotonic()
        try:
            log.info("Tool call", {"tool": "withings_list_devices"})
            body = client.request("/v2/user", {"action": "getdevice"})
            devices = (body or {}).get("devices") if isinstance(body, dict) else None
            log.info(
                "Tool done",
                {
                    "tool": "withings_list_devices",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "count": len(devices) if isinstance(devices, list) else None,
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error("Tool failed", {"tool": "withings_list_devices", "error": str(e)})
            raise ToolError(str(e)) from e

    @mcp.tool(
        name="withings_get_goals",
        description=(
            "Get health goals configured in the Withings account (e.g. steps, weight, sleep "
            "targets), if the user has set any."
        ),
    )
    def withings_get_goals() -> dict[str, Any]:
        started = time.monotonic()
        try:
            log.info("Tool call", {"tool": "withings_get_goals"})
            body = client.request("/v2/user", {"action": "getgoals"})
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_goals",
                    "durationMs": int((time.monotonic() - started) * 1000),
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error("Tool failed", {"tool": "withings_get_goals", "error": str(e)})
            raise ToolError(str(e)) from e
