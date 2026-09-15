import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname } from "node:path";
import { log } from "../log.js";
import { refreshAccessToken } from "../auth/oauth.js";
import {
  WITHINGS_API_BASE,
  type TokenSet,
  type WithingsEnvelope,
} from "./types.js";

export interface WithingsClientOptions {
  clientId: string;
  clientSecret: string;
  refreshToken: string;
  tokenFile?: string;
}

export class WithingsClient {
  private clientId: string;
  private clientSecret: string;
  private tokens: TokenSet;
  private tokenFile?: string;
  private refreshPromise: Promise<void> | null = null;

  constructor(opts: WithingsClientOptions) {
    this.clientId = opts.clientId;
    this.clientSecret = opts.clientSecret;
    this.tokenFile = opts.tokenFile;

    const fromFile = opts.tokenFile ? loadTokenFile(opts.tokenFile) : null;
    this.tokens = {
      access_token: fromFile?.access_token ?? "",
      refresh_token: fromFile?.refresh_token ?? opts.refreshToken,
      userid: fromFile?.userid,
      expires_in: fromFile?.expires_in,
      expires_at: fromFile?.expires_at,
      scope: fromFile?.scope,
    };

    if (!this.tokens.refresh_token) {
      throw new Error(
        "Missing refresh token. Set WITHINGS_REFRESH_TOKEN or provide a token file from `withings-mcp auth`.",
      );
    }
  }

  async ensureAccessToken(): Promise<string> {
    const now = Math.floor(Date.now() / 1000);
    const skew = 60;
    if (
      this.tokens.access_token &&
      this.tokens.expires_at &&
      this.tokens.expires_at > now + skew
    ) {
      return this.tokens.access_token;
    }

    if (!this.refreshPromise) {
      this.refreshPromise = this.doRefresh().finally(() => {
        this.refreshPromise = null;
      });
    }
    await this.refreshPromise;
    return this.tokens.access_token;
  }

  private async doRefresh(): Promise<void> {
    const next = await refreshAccessToken({
      clientId: this.clientId,
      clientSecret: this.clientSecret,
      refreshToken: this.tokens.refresh_token,
    });
    this.tokens = next;
    this.persistTokens();
  }

  private persistTokens(): void {
    if (!this.tokenFile) {
      log.debug("No TOKEN_FILE configured; rotated refresh token kept in memory only");
      return;
    }
    try {
      const dir = dirname(this.tokenFile);
      if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
      writeFileSync(this.tokenFile, JSON.stringify(this.tokens, null, 2), {
        mode: 0o600,
      });
      log.info("Persisted rotated tokens to TOKEN_FILE", {
        tokenFile: this.tokenFile,
      });
    } catch (e) {
      log.warn("Failed to persist token file; refresh token may be lost on restart", {
        tokenFile: this.tokenFile,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }

  async request<T = unknown>(
    path: string,
    params: Record<string, string | number | undefined>,
  ): Promise<T> {
    const action = String(params.action ?? "");
    const started = Date.now();

    const doCall = async (accessToken: string) => {
      const body = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v === undefined || v === "") continue;
        body.set(k, String(v));
      }

      log.debug("Withings API request", { path, action, params: summarizeParams(params) });

      const res = await fetch(`${WITHINGS_API_BASE}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
          Authorization: `Bearer ${accessToken}`,
        },
        body,
      });

      const json = (await res.json()) as WithingsEnvelope<T>;
      return { httpStatus: res.status, json };
    };

    let accessToken = await this.ensureAccessToken();
    let { httpStatus, json } = await doCall(accessToken);

    // 343 = invalid/expired access token — refresh once and retry
    if (json.status === 343) {
      log.warn("Access token rejected (343); refreshing and retrying", { path, action });
      await this.doRefresh();
      accessToken = this.tokens.access_token;
      ({ httpStatus, json } = await doCall(accessToken));
    }

    const durationMs = Date.now() - started;

    if (json.status !== 0 && json.status !== 100) {
      log.error("Withings API error", {
        path,
        action,
        status: json.status,
        error: json.error,
        httpStatus,
        durationMs,
      });
      throw new Error(
        `Withings API error path=${path} action=${action} status=${json.status}: ${json.error ?? "unknown"}`,
      );
    }

    log.info("Withings API ok", {
      path,
      action,
      status: json.status,
      durationMs,
      empty: json.status === 100,
    });

    log.debug("Withings API response meta", {
      path,
      action,
      more: (json.body as { more?: number } | undefined)?.more,
      offset: (json.body as { offset?: number } | undefined)?.offset,
    });

    return (json.body ?? {}) as T;
  }
}

function loadTokenFile(path: string): TokenSet | null {
  try {
    if (!existsSync(path)) return null;
    const raw = readFileSync(path, "utf8");
    const parsed = JSON.parse(raw) as TokenSet;
    if (!parsed.refresh_token) return null;
    log.info("Loaded tokens from TOKEN_FILE", { tokenFile: path });
    return parsed;
  } catch (e) {
    log.warn("Could not read TOKEN_FILE", {
      tokenFile: path,
      error: e instanceof Error ? e.message : String(e),
    });
    return null;
  }
}

function summarizeParams(
  params: Record<string, string | number | undefined>,
): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "") continue;
    out[k] = v;
  }
  return out;
}

export function requireEnv(name: string): string {
  const v = process.env[name]?.trim();
  if (!v) throw new Error(`Missing required environment variable: ${name}`);
  return v;
}

export function createClientFromEnv(): WithingsClient {
  const clientId = requireEnv("WITHINGS_CLIENT_ID");
  const clientSecret = requireEnv("WITHINGS_CLIENT_SECRET");
  const refreshToken = process.env.WITHINGS_REFRESH_TOKEN?.trim() ?? "";
  const tokenFile =
    process.env.WITHINGS_TOKEN_FILE?.trim() ||
    (existsSync("/data") ? "/data/tokens.json" : undefined);

  log.info("Creating Withings client", {
    clientIdConfigured: Boolean(clientId),
    clientSecretConfigured: Boolean(clientSecret),
    refreshTokenConfigured: Boolean(refreshToken) || Boolean(tokenFile),
    tokenFileConfigured: Boolean(tokenFile),
    tokenFile: tokenFile ?? null,
  });

  return new WithingsClient({
    clientId,
    clientSecret,
    refreshToken,
    tokenFile,
  });
}
