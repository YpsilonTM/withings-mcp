/** Withings Public API base URL */
export const WITHINGS_API_BASE = "https://wbsapi.withings.net";
export const WITHINGS_AUTH_URL =
  "https://account.withings.com/oauth2_user/authorize2";

export const DEFAULT_SCOPES =
  "user.info,user.metrics,user.activity,user.sleepevents";

export interface WithingsEnvelope<T = unknown> {
  status: number;
  body?: T;
  error?: string;
}

export interface TokenSet {
  access_token: string;
  refresh_token: string;
  userid?: string | number;
  expires_in?: number;
  scope?: string;
  /** unix seconds when access_token expires (computed locally) */
  expires_at?: number;
}

export interface Measure {
  value: number;
  type: number;
  unit: number;
  algo?: number;
  fm?: number;
}

export interface MeasureGroup {
  grpid: number;
  attrib: number;
  date: number;
  created: number;
  category: number;
  deviceid?: string;
  hash_deviceid?: string;
  measures: Measure[];
  comment?: string;
}

export interface GetMeasBody {
  updatetime: number;
  timezone: string;
  measuregrps: MeasureGroup[];
  more?: number;
  offset?: number;
}

export interface DecodedMeasure {
  type: number;
  name: string;
  value: number;
  unit: string;
  raw_value: number;
  raw_unit: number;
}

export interface DecodedMeasureGroup {
  grpid: number;
  date: number;
  date_iso: string;
  category: number;
  measures: DecodedMeasure[];
}

/** Measurement type IDs used by Measure getmeas */
export const MEASURE_TYPES: Record<
  number,
  { name: string; unit: string }
> = {
  1: { name: "Weight", unit: "kg" },
  4: { name: "Height", unit: "m" },
  5: { name: "Fat Free Mass", unit: "kg" },
  6: { name: "Fat Ratio", unit: "%" },
  8: { name: "Fat Mass Weight", unit: "kg" },
  9: { name: "Diastolic Blood Pressure", unit: "mmHg" },
  10: { name: "Systolic Blood Pressure", unit: "mmHg" },
  11: { name: "Heart Rate", unit: "bpm" },
  12: { name: "Temperature", unit: "°C" },
  54: { name: "SpO2", unit: "%" },
  71: { name: "Body Temperature", unit: "°C" },
  73: { name: "Skin Temperature", unit: "°C" },
  76: { name: "Muscle Mass", unit: "kg" },
  77: { name: "Hydration", unit: "kg" },
  88: { name: "Bone Mass", unit: "kg" },
  91: { name: "Pulse Wave Velocity", unit: "m/s" },
  123: { name: "VO2 Max", unit: "ml/min/kg" },
  130: { name: "Atrial Fibrillation (QRS)", unit: "" },
  135: { name: "QRS Interval", unit: "ms" },
  136: { name: "PR Interval", unit: "ms" },
  137: { name: "QT Interval", unit: "ms" },
  138: { name: "Corrected QT Interval", unit: "ms" },
  139: { name: "Atrial Fibrillation from PPG", unit: "" },
  140: { name: "Vascular Age", unit: "years" },
};

export const MEASTYPE_GROUPS = {
  weight: [1],
  body_composition: [5, 6, 8, 76, 77, 88],
  blood_pressure: [9, 10, 11],
  heart_rate: [11],
  body_temperature: [12, 71, 73],
  spo2: [54],
} as const;

export function decodeMeasureValue(value: number, unit: number): number {
  return value * Math.pow(10, unit);
}

export function decodeMeasure(m: Measure): DecodedMeasure {
  const meta = MEASURE_TYPES[m.type] ?? {
    name: `Unknown(${m.type})`,
    unit: "",
  };
  return {
    type: m.type,
    name: meta.name,
    value: decodeMeasureValue(m.value, m.unit),
    unit: meta.unit,
    raw_value: m.value,
    raw_unit: m.unit,
  };
}

export function decodeMeasureGroups(
  groups: MeasureGroup[],
): DecodedMeasureGroup[] {
  return groups.map((g) => ({
    grpid: g.grpid,
    date: g.date,
    date_iso: new Date(g.date * 1000).toISOString(),
    category: g.category,
    measures: g.measures.map(decodeMeasure),
  }));
}
