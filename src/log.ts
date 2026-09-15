export type LogLevel = "error" | "warn" | "info" | "debug";

const LEVEL_ORDER: Record<LogLevel, number> = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3,
};

function parseLevel(raw: string | undefined): LogLevel {
  const v = (raw ?? "info").toLowerCase();
  if (v === "error" || v === "warn" || v === "info" || v === "debug") return v;
  return "info";
}

let currentLevel: LogLevel = parseLevel(process.env.WITHINGS_LOG_LEVEL);

export function setLogLevel(level: LogLevel): void {
  currentLevel = level;
}

export function getLogLevel(): LogLevel {
  return currentLevel;
}

type LogFields = Record<string, unknown>;

function write(level: LogLevel, msg: string, fields?: LogFields): void {
  if (LEVEL_ORDER[level] > LEVEL_ORDER[currentLevel]) return;
  const entry: Record<string, unknown> = {
    ts: new Date().toISOString(),
    level,
    msg,
    ...sanitize(fields ?? {}),
  };
  // stdout is reserved for MCP JSON-RPC
  process.stderr.write(`${JSON.stringify(entry)}\n`);
}

const SECRET_KEYS = new Set([
  "access_token",
  "refresh_token",
  "client_secret",
  "authorization",
  "code",
]);

function sanitize(fields: LogFields): LogFields {
  const out: LogFields = {};
  for (const [key, value] of Object.entries(fields)) {
    const lower = key.toLowerCase();
    const isSecretValue =
      SECRET_KEYS.has(lower) ||
      lower.endsWith("_token") ||
      lower === "token" ||
      lower.endsWith("_secret") ||
      lower === "secret" ||
      lower === "authorization" ||
      lower === "code";
    // Allow boolean *Configured flags and tokenFile path metadata
    const isMeta =
      lower.endsWith("configured") ||
      lower === "tokenfile" ||
      lower === "token_file" ||
      lower === "writepath";
    if (isSecretValue && !isMeta) {
      out[key] = value == null || value === "" ? false : "[redacted]";
      continue;
    }
    out[key] = value;
  }
  return out;
}

export const log = {
  error(msg: string, fields?: LogFields): void {
    write("error", msg, fields);
  },
  warn(msg: string, fields?: LogFields): void {
    write("warn", msg, fields);
  },
  info(msg: string, fields?: LogFields): void {
    write("info", msg, fields);
  },
  debug(msg: string, fields?: LogFields): void {
    write("debug", msg, fields);
  },
};
