"""Activity / intraday / workout tools."""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from withings_mcp.log import log
from withings_mcp.tools.helpers import iter_unix_windows, resolve_unix_range, resolve_ymd_range
from withings_mcp.withings.client import WithingsClient

DEFAULT_ACTIVITY_FIELDS = (
    "steps,distance,elevation,soft,moderate,intense,active,calories,totalcalories,"
    "hr_average,hr_min,hr_max,hr_zone_0,hr_zone_1,hr_zone_2,hr_zone_3"
)

DEFAULT_INTRADAY_FIELDS = (
    "steps,elevation,calories,distance,heart_rate,spo2_auto,rr,duration,stroke,pool_lap,"
    "rmssd,sdnn1,hrv_quality,core_body_temperature,chest_movement_rate"
)

MAX_INTRADAY_SPAN = 24 * 3600


def fetch_intraday_activity(
    client: WithingsClient,
    startdate: int,
    enddate: int,
    data_fields: str,
) -> dict[str, Any]:
    """Fetch intraday activity, splitting into ≤24h windows when needed."""
    windows = iter_unix_windows(startdate, enddate, max_span=MAX_INTRADAY_SPAN)
    if len(windows) > 1:
        log.warn(
            "Intraday window split into 24h chunks",
            {
                "requestedHours": (enddate - startdate) / 3600,
                "chunks": len(windows),
            },
        )

    merged_series: dict[str, Any] = {}
    last_body: dict[str, Any] = {}
    for w_start, w_end in windows:
        body = client.request(
            "/v2/measure",
            {
                "action": "getintradayactivity",
                "startdate": w_start,
                "enddate": w_end,
                "data_fields": data_fields,
            },
        )
        last_body = body if isinstance(body, dict) else {}
        series = last_body.get("series")
        if isinstance(series, dict):
            merged_series.update(series)

    result = dict(last_body)
    if merged_series or "series" in result:
        result["series"] = merged_series
    result["windows"] = [{"startdate": s, "enddate": e} for s, e in windows]
    return result


def register_activity_tools(mcp: FastMCP, client: WithingsClient) -> None:
    @mcp.tool(
        name="withings_get_activity",
        description=(
            "Fetch daily activity summaries from the watch/tracker (steps, distance, calories, "
            "HR zones, etc.). Prefer this for day-level watch stats; use "
            "withings_get_intraday_activity for minute-level series."
        ),
    )
    def withings_get_activity(
        startdateymd: Annotated[str | None, "Start date YYYY-MM-DD. Default: 7 days ago."] = None,
        enddateymd: Annotated[str | None, "End date YYYY-MM-DD. Default: today UTC."] = None,
        data_fields: Annotated[
            str | None,
            f"Comma-separated activity fields. Default: {DEFAULT_ACTIVITY_FIELDS}",
        ] = None,
        offset: Annotated[int | None, "Pagination offset."] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start_ymd, end_ymd = resolve_ymd_range(startdateymd=startdateymd, enddateymd=enddateymd)
            log.info(
                "Tool call",
                {
                    "tool": "withings_get_activity",
                    "startdateymd": start_ymd,
                    "enddateymd": end_ymd,
                },
            )
            body = client.request(
                "/v2/measure",
                {
                    "action": "getactivity",
                    "startdateymd": start_ymd,
                    "enddateymd": end_ymd,
                    "data_fields": data_fields or DEFAULT_ACTIVITY_FIELDS,
                    "offset": offset,
                },
            )
            activities = (body or {}).get("activities") if isinstance(body, dict) else None
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_activity",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "count": len(activities) if isinstance(activities, list) else None,
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error("Tool failed", {"tool": "withings_get_activity", "error": str(e)})
            raise ToolError(str(e)) from e

    @mcp.tool(
        name="withings_get_intraday_activity",
        description=(
            "Fetch high-resolution watch/tracker series for up to 24 hours: heart_rate, "
            "core_body_temperature, spo2_auto, steps, HRV, etc. This is the main source for "
            "continuous vitals from a Withings watch (not the scale). Withings returns at most "
            "24 hours per call; longer ranges are split automatically."
        ),
    )
    def withings_get_intraday_activity(
        startdate: Annotated[int | None, "Start unix timestamp. Default: 24h ago."] = None,
        enddate: Annotated[int | None, "End unix timestamp. Default: now."] = None,
        data_fields: Annotated[
            str | None,
            f"Comma-separated fields. Default: {DEFAULT_INTRADAY_FIELDS}",
        ] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start, end = resolve_unix_range(startdate=startdate, enddate=enddate)
            log.info(
                "Tool call",
                {
                    "tool": "withings_get_intraday_activity",
                    "startdate": start,
                    "enddate": end,
                },
            )
            body = fetch_intraday_activity(
                client,
                start,
                end,
                data_fields or DEFAULT_INTRADAY_FIELDS,
            )
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_intraday_activity",
                    "durationMs": int((time.monotonic() - started) * 1000),
                },
            )
            return body
        except Exception as e:
            log.error(
                "Tool failed",
                {"tool": "withings_get_intraday_activity", "error": str(e)},
            )
            raise ToolError(str(e)) from e

    @mcp.tool(
        name="withings_get_workouts",
        description=(
            "Fetch logged workouts from the watch/activity tracker for a date range "
            "(default last 7 days). Includes session type, duration, and optional metrics like "
            "calories, HR, distance, steps."
        ),
    )
    def withings_get_workouts(
        startdateymd: Annotated[str | None, "Start date YYYY-MM-DD. Default: 7 days ago."] = None,
        enddateymd: Annotated[str | None, "End date YYYY-MM-DD. Default: today UTC."] = None,
        data_fields: Annotated[
            str | None,
            "Optional workout data fields (e.g. calories,hr_average,hr_min,hr_max,"
            "distance,steps,elevation).",
        ] = None,
        offset: Annotated[int | None, "Pagination offset."] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start_ymd, end_ymd = resolve_ymd_range(startdateymd=startdateymd, enddateymd=enddateymd)
            log.info(
                "Tool call",
                {
                    "tool": "withings_get_workouts",
                    "startdateymd": start_ymd,
                    "enddateymd": end_ymd,
                },
            )
            body = client.request(
                "/v2/measure",
                {
                    "action": "getworkouts",
                    "startdateymd": start_ymd,
                    "enddateymd": end_ymd,
                    "data_fields": data_fields,
                    "offset": offset,
                },
            )
            series = (body or {}).get("series") if isinstance(body, dict) else None
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_workouts",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "count": len(series) if isinstance(series, list) else None,
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error("Tool failed", {"tool": "withings_get_workouts", "error": str(e)})
            raise ToolError(str(e)) from e
