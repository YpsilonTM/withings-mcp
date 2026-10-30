"""Withings API constants and measure decoding (ported from TypeScript)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

WITHINGS_API_BASE = "https://wbsapi.withings.net"
WITHINGS_AUTH_URL = "https://account.withings.com/oauth2_user/authorize2"

DEFAULT_SCOPES = "user.info,user.metrics,user.activity,user.sleepevents"


class TokenSet(TypedDict, total=False):
    access_token: str
    refresh_token: str
    userid: str | int
    expires_in: int
    scope: str
    expires_at: int


class Measure(TypedDict, total=False):
    value: int
    type: int
    unit: int
    algo: int
    fm: int


class MeasureGroup(TypedDict, total=False):
    grpid: int
    attrib: int
    date: int
    created: int
    category: int
    deviceid: str
    hash_deviceid: str
    measures: list[Measure]
    comment: str


class GetMeasBody(TypedDict, total=False):
    updatetime: int
    timezone: str
    measuregrps: list[MeasureGroup]
    more: int
    offset: int


MEASURE_TYPES: dict[int, dict[str, str]] = {
    1: {"name": "Weight", "unit": "kg"},
    4: {"name": "Height", "unit": "m"},
    5: {"name": "Fat Free Mass", "unit": "kg"},
    6: {"name": "Fat Ratio", "unit": "%"},
    8: {"name": "Fat Mass Weight", "unit": "kg"},
    9: {"name": "Diastolic Blood Pressure", "unit": "mmHg"},
    10: {"name": "Systolic Blood Pressure", "unit": "mmHg"},
    11: {"name": "Heart Rate", "unit": "bpm"},
    12: {"name": "Temperature", "unit": "°C"},
    54: {"name": "SpO2", "unit": "%"},
    71: {"name": "Body Temperature", "unit": "°C"},
    73: {"name": "Skin Temperature", "unit": "°C"},
    76: {"name": "Muscle Mass", "unit": "kg"},
    77: {"name": "Hydration", "unit": "kg"},
    88: {"name": "Bone Mass", "unit": "kg"},
    91: {"name": "Pulse Wave Velocity", "unit": "m/s"},
    123: {"name": "VO2 Max", "unit": "ml/min/kg"},
    130: {"name": "Atrial Fibrillation (QRS)", "unit": ""},
    135: {"name": "QRS Interval", "unit": "ms"},
    136: {"name": "PR Interval", "unit": "ms"},
    137: {"name": "QT Interval", "unit": "ms"},
    138: {"name": "Corrected QT Interval", "unit": "ms"},
    139: {"name": "Atrial Fibrillation from PPG", "unit": ""},
    140: {"name": "Vascular Age", "unit": "years"},
}

MEASTYPE_GROUPS: dict[str, list[int]] = {
    "weight": [1],
    "body_composition": [5, 6, 8, 76, 77, 88],
    "blood_pressure": [9, 10, 11],
    "heart_rate": [11],
    "body_temperature": [12, 71, 73],
    "spo2": [54],
}


def decode_measure_value(value: int | float, unit: int) -> float:
    return value * (10**unit)


def decode_measure(m: Measure | dict[str, Any]) -> dict[str, Any]:
    mtype = int(m["type"])
    meta = MEASURE_TYPES.get(mtype, {"name": f"Unknown({mtype})", "unit": ""})
    raw_value = m["value"]
    raw_unit = m["unit"]
    return {
        "type": mtype,
        "name": meta["name"],
        "value": decode_measure_value(raw_value, raw_unit),
        "unit": meta["unit"],
        "raw_value": raw_value,
        "raw_unit": raw_unit,
    }


def decode_measure_groups(
    groups: list[MeasureGroup] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in groups:
        date = int(g["date"])
        date_iso = datetime.fromtimestamp(date, tz=UTC).isoformat().replace("+00:00", "Z")
        out.append(
            {
                "grpid": g["grpid"],
                "date": date,
                "date_iso": date_iso,
                "category": g["category"],
                "measures": [decode_measure(m) for m in g.get("measures", [])],
            }
        )
    return out
