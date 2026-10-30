"""Measurement tools (getmeas + spot/intraday hybrids)."""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from withings_mcp.log import get_log_level, log
from withings_mcp.tools.helpers import resolve_unix_range
from withings_mcp.withings.client import WithingsClient
from withings_mcp.withings.types import MEASTYPE_GROUPS, MEASURE_TYPES, decode_measure_groups


def get_meas(
    client: WithingsClient,
    meastypes: list[int] | None,
    startdate: int,
    enddate: int,
    offset: int | None = None,
) -> dict[str, Any]:
    body = client.request(
        "/measure",
        {
            "action": "getmeas",
            "startdate": startdate,
            "enddate": enddate,
            "meastypes": ",".join(str(t) for t in meastypes) if meastypes else None,
            "offset": offset,
        },
    )
    groups = decode_measure_groups(body.get("measuregrps") or [])
    log.info(
        "Decoded measurements",
        {
            "tool": "withings_get_measurements",
            "groupCount": len(groups),
            "more": body.get("more"),
            "offset": body.get("offset"),
        },
    )
    more = bool(body.get("more"))
    return {
        "updatetime": body.get("updatetime"),
        "timezone": body.get("timezone"),
        "more": more,
        "offset": body.get("offset") or 0,
        "count": len(groups),
        "measuregrps": groups,
        "note": "More data available; call again with the returned offset." if more else None,
    }


def _run_typed_meas(
    client: WithingsClient,
    tool_name: str,
    meastypes: list[int],
    startdate: int | None,
    enddate: int | None,
    offset: int | None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        start, end = resolve_unix_range(startdate=startdate, enddate=enddate)
        log.info(
            "Tool call",
            {
                "tool": tool_name,
                "startdate": start,
                "enddate": end,
                "meastypes": meastypes,
                "offset": offset,
            },
        )
        data = get_meas(client, meastypes, start, end, offset)
        log.info(
            "Tool done",
            {
                "tool": tool_name,
                "durationMs": int((time.monotonic() - started) * 1000),
                "count": data["count"],
            },
        )
        return data
    except Exception as e:
        log.error("Tool failed", {"tool": tool_name, "error": str(e)})
        raise ToolError(str(e)) from e


def register_measure_tools(mcp: FastMCP, client: WithingsClient) -> None:
    @mcp.tool(
        name="withings_get_measure_types",
        description=(
            "List known Withings measurement type IDs used by getmeas (weight, BP, SpO2, "
            "spot temperature, etc.). No API call. For continuous watch vitals (HR, core temp, "
            "SpO2), prefer withings_get_intraday_activity instead of these spot types."
        ),
    )
    def withings_get_measure_types() -> dict[str, Any]:
        log.info("Tool call", {"tool": "withings_get_measure_types"})
        return {
            "types": [{"type": tid, **meta} for tid, meta in MEASURE_TYPES.items()],
            "groups": MEASTYPE_GROUPS,
        }

    @mcp.tool(
        name="withings_get_measurements",
        description=(
            "Fetch spot/scale health measurements via getmeas (weight, composition, BP, spot "
            "HR/temp/SpO2, etc.). Optionally filter by meastypes. Values are decoded "
            "(value * 10^unit). This is NOT the main source for continuous watch vitals — use "
            "withings_get_intraday_activity (or withings_get_heart_rate / "
            "withings_get_body_temperature with include_intraday=true) for those."
        ),
    )
    def withings_get_measurements(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[
            int | None, "Pagination offset from a previous more=true response."
        ] = None,
        meastypes: Annotated[
            list[int] | None,
            "Spot measurement type IDs to include. Omit for all. Use withings_get_measure_types "
            "for the catalog. Continuous watch metrics are not in this list.",
        ] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start, end = resolve_unix_range(startdate=startdate, enddate=enddate)
            log.info(
                "Tool call",
                {
                    "tool": "withings_get_measurements",
                    "startdate": start,
                    "enddate": end,
                    "meastypes": meastypes,
                    "offset": offset,
                },
            )
            data = get_meas(client, meastypes, start, end, offset)
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_measurements",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "count": data["count"],
                },
            )
            return data
        except Exception as e:
            fields: dict[str, Any] = {
                "tool": "withings_get_measurements",
                "error": str(e),
            }
            if get_log_level() == "debug":
                fields["stack"] = str(e)
            log.error("Tool failed", fields)
            raise ToolError(str(e)) from e

    @mcp.tool(
        name="withings_get_weight",
        description=(
            "Fetch scale weight measurements (meastype 1). Typical source: Withings scale."
        ),
    )
    def withings_get_weight(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[
            int | None, "Pagination offset from a previous more=true response."
        ] = None,
    ) -> dict[str, Any]:
        return _run_typed_meas(
            client,
            "withings_get_weight",
            list(MEASTYPE_GROUPS["weight"]),
            startdate,
            enddate,
            offset,
        )

    @mcp.tool(
        name="withings_get_body_composition",
        description=(
            "Fetch scale body composition: fat free mass, fat ratio, fat mass, muscle, hydration, "
            "bone (types 5,6,8,76,77,88). Typical source: Withings scale."
        ),
    )
    def withings_get_body_composition(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[
            int | None, "Pagination offset from a previous more=true response."
        ] = None,
    ) -> dict[str, Any]:
        return _run_typed_meas(
            client,
            "withings_get_body_composition",
            list(MEASTYPE_GROUPS["body_composition"]),
            startdate,
            enddate,
            offset,
        )

    @mcp.tool(
        name="withings_get_blood_pressure",
        description=(
            "Fetch blood pressure and related spot pulse "
            "(diastolic 9, systolic 10, heart rate 11). "
            "Typical source: BPM or scale, not continuous watch HR."
        ),
    )
    def withings_get_blood_pressure(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[
            int | None, "Pagination offset from a previous more=true response."
        ] = None,
    ) -> dict[str, Any]:
        return _run_typed_meas(
            client,
            "withings_get_blood_pressure",
            list(MEASTYPE_GROUPS["blood_pressure"]),
            startdate,
            enddate,
            offset,
        )

    @mcp.tool(
        name="withings_get_spo2",
        description=(
            "Fetch spot SpO2 measurements (meastype 54) from getmeas. For continuous watch SpO2, "
            "prefer withings_get_intraday_activity with spo2_auto."
        ),
    )
    def withings_get_spo2(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[
            int | None, "Pagination offset from a previous more=true response."
        ] = None,
    ) -> dict[str, Any]:
        return _run_typed_meas(
            client,
            "withings_get_spo2",
            list(MEASTYPE_GROUPS["spo2"]),
            startdate,
            enddate,
            offset,
        )

    @mcp.tool(
        name="withings_get_body_temperature",
        description=(
            "Fetch body temperature. Spot readings (meastypes 12/71/73 via getmeas) come from "
            "thermometers or occasional device measures. For Withings watches, set "
            "include_intraday=true to fetch continuous core_body_temperature (max 24h window) — "
            "that is usually where watch temp lives."
        ),
    )
    def withings_get_body_temperature(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[
            int | None, "Pagination offset from a previous more=true response."
        ] = None,
        include_intraday: Annotated[
            bool | None,
            "If true, also fetch watch intraday core_body_temperature via getintradayactivity "
            "(capped to 24h). Recommended for ScanWatch / activity trackers.",
        ] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start, end = resolve_unix_range(startdate=startdate, enddate=enddate)
            log.info(
                "Tool call",
                {
                    "tool": "withings_get_body_temperature",
                    "startdate": start,
                    "enddate": end,
                    "include_intraday": include_intraday or False,
                },
            )
            spot = get_meas(
                client,
                list(MEASTYPE_GROUPS["body_temperature"]),
                start,
                end,
                offset,
            )
            intraday: Any = None
            if include_intraday:
                max_span = 24 * 3600
                if end - start > max_span:
                    start = end - max_span
                    log.warn(
                        "Intraday temperature window capped to 24h",
                        {"startdate": start, "enddate": end},
                    )
                intraday = client.request(
                    "/v2/measure",
                    {
                        "action": "getintradayactivity",
                        "startdate": start,
                        "enddate": end,
                        "data_fields": "core_body_temperature",
                    },
                )
            result = {"spot_measurements": spot, "intraday": intraday}
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_body_temperature",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "spotCount": spot["count"],
                    "include_intraday": bool(include_intraday),
                },
            )
            return result
        except Exception as e:
            log.error(
                "Tool failed",
                {"tool": "withings_get_body_temperature", "error": str(e)},
            )
            raise ToolError(str(e)) from e

    @mcp.tool(
        name="withings_get_heart_rate",
        description=(
            "Fetch heart rate. Spot readings (meastype 11 via getmeas) come from scale/BPM when "
            "you take a measurement. For Withings watches, set include_intraday=true (or use "
            "withings_get_intraday_activity) for continuous HR — that is usually where watch HR "
            "lives (max 24h window)."
        ),
    )
    def withings_get_heart_rate(
        startdate: Annotated[
            int | None, "Start unix timestamp (seconds). Default: 24h ago."
        ] = None,
        enddate: Annotated[int | None, "End unix timestamp (seconds). Default: now."] = None,
        offset: Annotated[
            int | None, "Pagination offset from a previous more=true response."
        ] = None,
        include_intraday: Annotated[
            bool | None,
            "If true, also fetch continuous watch heart_rate via getintradayactivity "
            "(capped to 24h). Recommended for ScanWatch / activity trackers.",
        ] = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        try:
            start, end = resolve_unix_range(startdate=startdate, enddate=enddate)
            log.info(
                "Tool call",
                {
                    "tool": "withings_get_heart_rate",
                    "startdate": start,
                    "enddate": end,
                    "include_intraday": include_intraday or False,
                },
            )
            spot = get_meas(
                client,
                list(MEASTYPE_GROUPS["heart_rate"]),
                start,
                end,
                offset,
            )
            intraday: Any = None
            if include_intraday:
                max_span = 24 * 3600
                if end - start > max_span:
                    start = end - max_span
                    log.warn(
                        "Intraday HR window capped to 24h",
                        {"startdate": start, "enddate": end},
                    )
                intraday = client.request(
                    "/v2/measure",
                    {
                        "action": "getintradayactivity",
                        "startdate": start,
                        "enddate": end,
                        "data_fields": "heart_rate",
                    },
                )
            result = {"spot_measurements": spot, "intraday": intraday}
            log.info(
                "Tool done",
                {
                    "tool": "withings_get_heart_rate",
                    "durationMs": int((time.monotonic() - started) * 1000),
                    "spotCount": spot["count"],
                    "include_intraday": bool(include_intraday),
                },
            )
            return result
        except Exception as e:
            log.error("Tool failed", {"tool": "withings_get_heart_rate", "error": str(e)})
            raise ToolError(str(e)) from e
