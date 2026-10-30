"""Sleep summary and series tools."""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from withings_mcp.log import log
from withings_mcp.tools.helpers import resolve_unix_range, resolve_ymd_range
from withings_mcp.withings.client import WithingsClient

DEFAULT_SUMMARY_FIELDS = (
    "nb_rem_episodes,sleep_score,snoring,snoringepisodecount,sleep_efficiency,"
    "asleepduration,deepsleepduration,lightsleepduration,remsleepduration,"
    "durationtosleep,durationtowakeup,out_of_bed_count,hr_average,hr_min,hr_max,"
    "rr_average,rr_min,rr_max,breathing_disturbances_intensity,total_timeinbed,"
    "total_sleep_time"
)

DEFAULT_SERIES_FIELDS = "hr,rr,snoring,sdnn_1,rmssd,hrv_quality,mvt_score,chest_movement_rate"


def register_sleep_tools(mcp: FastMCP, client: WithingsClient) -> None:
    @mcp.tool(
        name="withings_get_sleep_summary",
        description=(
            "Fetch per-night sleep summaries (score, stages, HR/RR stats, snoring, etc.). "
            "Default range is the last 7 days. Typical sources: Sleep Analyzer / Sleep Mat, or "
            "watch sleep tracking. For minute-level detail within a night, use withings_get_sleep."
        ),
    )
    def withings_get_sleep_summary(
        startdateymd: Annotated[str | None, "Start date YYYY-MM-DD. Default: 7 days ago."] = None,
        enddateymd: Annotated[str | None, "End date YYYY-MM-DD. Default: today UTC."] = None,
        data_fields: Annotated[
            str | None,
            "Comma-separated fields. Default includes score, stages, HR/RR.",
        ] = None,
        lastupdate: Annotated[
            int | None,
            "Only return nights updated after this unix timestamp. When set, date range "
            "params are omitted.",
        ] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start_ymd, end_ymd = resolve_ymd_range(startdateymd=startdateymd, enddateymd=enddateymd)
            log.info(
                "Tool call",
                {
                    "tool": "withings_get_sleep_summary",
                    "startdateymd": start_ymd,
                    "enddateymd": end_ymd,
                    "lastupdate": lastupdate,
                },
            )
            body = client.request(
                "/v2/sleep",
                {
                    "action": "getsummary",
                    "startdateymd": None if lastupdate is not None else start_ymd,
                    "enddateymd": None if lastupdate is not None else end_ymd,
                    "data_fields": data_fields or DEFAULT_SUMMARY_FIELDS,
                    "lastupdate": lastupdate,
                },
            )
            series = (body or {}).get("series") if isinstance(body, dict) else None
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_sleep_summary",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "count": len(series) if isinstance(series, list) else None,
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error(
                "Tool failed",
                {"tool": "withings_get_sleep_summary", "error": str(e)},
            )
            raise ToolError(str(e)) from e

    @mcp.tool(
        name="withings_get_sleep",
        description=(
            "Fetch high-frequency sleep stage and vital series for a time window (Sleep get): "
            "stages, HR, respiration, snoring, HRV, etc. Default range is the last 24 hours. "
            "Prefer withings_get_sleep_summary for multi-night overviews; use this for detailed "
            "series within a night. Typical sources: Sleep Analyzer / Sleep Mat, or watch sleep "
            "tracking."
        ),
    )
    def withings_get_sleep(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        data_fields: Annotated[
            str | None,
            f"Comma-separated series fields. Default: {DEFAULT_SERIES_FIELDS}",
        ] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start, end = resolve_unix_range(startdate=startdate, enddate=enddate, default_hours=24)
            log.info(
                "Tool call",
                {"tool": "withings_get_sleep", "startdate": start, "enddate": end},
            )
            body = client.request(
                "/v2/sleep",
                {
                    "action": "get",
                    "startdate": start,
                    "enddate": end,
                    "data_fields": data_fields or DEFAULT_SERIES_FIELDS,
                },
            )
            series = (body or {}).get("series") if isinstance(body, dict) else None
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_sleep",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "count": len(series) if isinstance(series, list) else None,
                },
            )
            return body if isinstance(body, dict) else {"data": body}
        except Exception as e:
            log.error("Tool failed", {"tool": "withings_get_sleep", "error": str(e)})
            raise ToolError(str(e)) from e
