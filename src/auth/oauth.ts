import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomBytes } from "node:crypto";
import { log } from "../log.js";
import {
  DEFAULT_SCOPES,
  WITHINGS_API_BASE,
  WITHINGS_AUTH_URL,
  type TokenSet,
  type WithingsEnvelope,
} from "../withings/types.js";

export interface AuthConfig {
  clientId: string;
  clientSecret: string;
  redirectPort?: number;
  scopes?: string;
}

export function buildAuthorizeUrl(
  clientId: string,
  redirectUri: string,
  scopes: string,
  state: string,
): string {
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: scopes,
    state,
  });
  return `${WITHINGS_AUTH_URL}?${params.toString()}`;
}

export async function exchangeAuthorizationCode(opts: {
  clientId: string;
  clientSecret: string;
  code: string;
  redirectUri: string;
}): Promise<TokenSet> {
  const body = new URLSearchParams({
    action: "requesttoken",
    grant_type: "authorization_code",
    client_id: opts.clientId,
    client_secret: opts.clientSecret,
    code: opts.code,
    redirect_uri: opts.redirectUri,
  });

  log.info("Exchanging authorization code for tokens");
  const res = await fetch(`${WITHINGS_API_BASE}/v2/oauth2`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  const json = (await res.json()) as WithingsEnvelope<TokenSet>;
  if (json.status !== 0 || !json.body?.access_token || !json.body?.refresh_token) {
    log.error("Token exchange failed", {
      status: json.status,
      error: json.error,
      httpStatus: res.status,
    });
    throw new Error(
      `Withings token exchange failed (status=${json.status}): ${json.error ?? "unknown"}`,
    );
  }

  const tokens: TokenSet = {
    ...json.body,
    expires_at: Math.floor(Date.now() / 1000) + (json.body.expires_in ?? 10800),
  };
  log.info("Token exchange succeeded", {
    status: json.status,
    userid: tokens.userid != null ? String(tokens.userid).slice(-4) : undefined,
    expires_in: tokens.expires_in,
    scope: tokens.scope,
  });
  return tokens;
}

export async function refreshAccessToken(opts: {
  clientId: string;
  clientSecret: string;
  refreshToken: string;
}): Promise<TokenSet> {
  const body = new URLSearchParams({
    action: "requesttoken",
    grant_type: "refresh_token",
    client_id: opts.clientId,
    client_secret: opts.clientSecret,
    refresh_token: opts.refreshToken,
  });

  log.info("Refreshing access token");
  const res = await fetch(`${WITHINGS_API_BASE}/v2/oauth2`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });

  const json = (await res.json()) as WithingsEnvelope<TokenSet>;
  if (json.status !== 0 || !json.body?.access_token || !json.body?.refresh_token) {
    log.error("Token refresh failed", {
      status: json.status,
      error: json.error,
      httpStatus: res.status,
    });
    throw new Error(
      `Withings token refresh failed (status=${json.status}): ${json.error ?? "unknown"}`,
    );
  }

  const tokens: TokenSet = {
    ...json.body,
    expires_at: Math.floor(Date.now() / 1000) + (json.body.expires_in ?? 10800),
  };
  log.info("Token refresh succeeded", {
    status: json.status,
    userid: tokens.userid != null ? String(tokens.userid).slice(-4) : undefined,
    expires_in: tokens.expires_in,
  });
  return tokens;
}

/**
 * Run interactive OAuth: local callback server, print authorize URL, wait for code.
 */
export async function runOAuthFlow(config: AuthConfig): Promise<TokenSet> {
  const port = config.redirectPort ?? Number(process.env.WITHINGS_REDIRECT_PORT ?? 8765);
  const redirectUri = `http://localhost:${port}/callback`;
  const scopes = config.scopes ?? DEFAULT_SCOPES;
  const state = randomBytes(16).toString("hex");

  const authorizeUrl = buildAuthorizeUrl(
    config.clientId,
    redirectUri,
    scopes,
    state,
  );

  log.info("Starting OAuth callback server", { port, redirectUri });

  const code = await new Promise<string>((resolve, reject) => {
    const server = createServer((req: IncomingMessage, res: ServerResponse) => {
      try {
        const url = new URL(req.url ?? "/", `http://localhost:${port}`);
        if (url.pathname !== "/callback") {
          res.writeHead(404);
          res.end("Not found");
          return;
        }

        const err = url.searchParams.get("error");
        if (err) {
          log.error("OAuth callback error", { error: err });
          res.writeHead(400, { "Content-Type": "text/html" });
          res.end(`<h1>Authorization failed</h1><p>${err}</p>`);
          server.close();
          reject(new Error(`OAuth error: ${err}`));
          return;
        }

        const returnedState = url.searchParams.get("state");
        if (returnedState !== state) {
          log.error("OAuth state mismatch");
          res.writeHead(400, { "Content-Type": "text/html" });
          res.end("<h1>Invalid state</h1>");
          server.close();
          reject(new Error("OAuth state mismatch"));
          return;
        }

        const authCode = url.searchParams.get("code");
        if (!authCode) {
          log.error("OAuth callback missing code");
          res.writeHead(400, { "Content-Type": "text/html" });
          res.end("<h1>Missing code</h1>");
          server.close();
          reject(new Error("Missing authorization code"));
          return;
        }

        log.info("OAuth callback received");
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end(
          "<h1>Authorization successful</h1><p>You can close this tab and return to the terminal.</p>",
        );
        server.close();
        resolve(authCode);
      } catch (e) {
        log.error("OAuth callback handler error", {
          error: e instanceof Error ? e.message : String(e),
        });
        res.writeHead(500);
        res.end("Internal error");
        server.close();
        reject(e);
      }
    });

    server.on("error", (e) => {
      log.error("OAuth server failed to listen", {
        error: e instanceof Error ? e.message : String(e),
        port,
      });
      reject(e);
    });

    server.listen(port, "0.0.0.0", () => {
      log.info("Open this URL in your browser to authorize", {
        authorizeUrl,
      });
      // Also print clearly for humans (stderr so it doesn't mix with token JSON on stdout)
      process.stderr.write(`\nAuthorize Withings access:\n${authorizeUrl}\n\n`);
    });
  });

  return exchangeAuthorizationCode({
    clientId: config.clientId,
    clientSecret: config.clientSecret,
    code,
    redirectUri,
  });
}
