#!/usr/bin/env node
import { writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname } from "node:path";
import { log, getLogLevel, setLogLevel, type LogLevel } from "./log.js";
import { runOAuthFlow } from "./auth/oauth.js";
import { requireEnv } from "./withings/client.js";
import { startMcpServer } from "./server.js";

function parseArgs(argv: string[]): {
  command: "mcp" | "auth" | "help";
  writePath?: string;
  port?: number;
} {
  const args = argv.slice(2);
  if (args.includes("-h") || args.includes("--help") || args[0] === "help") {
    return { command: "help" };
  }

  const command = (args[0] === "auth" ? "auth" : "mcp") as "mcp" | "auth";
  let writePath: string | undefined;
  let port: number | undefined;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--write" && args[i + 1]) {
      writePath = args[++i];
    } else if (args[i] === "--port" && args[i + 1]) {
      port = Number(args[++i]);
    } else if (args[i]?.startsWith("--write=")) {
      writePath = args[i].slice("--write=".length);
    } else if (args[i]?.startsWith("--port=")) {
      port = Number(args[i].slice("--port=".length));
    }
  }

  return { command, writePath, port };
}

function printHelp(): void {
  // Auth helper may print help to stdout; MCP mode should use stderr
  const text = `
withings-mcp — Withings Model Context Protocol server

Usage:
  withings-mcp              Start MCP server on stdio (default)
  withings-mcp auth         Run one-time OAuth and print tokens as JSON
  withings-mcp auth --write /path/tokens.json
  withings-mcp auth --port 8765

Environment:
  WITHINGS_CLIENT_ID        Required
  WITHINGS_CLIENT_SECRET    Required
  WITHINGS_REFRESH_TOKEN    Required for MCP (from auth)
  WITHINGS_TOKEN_FILE       Optional path to persist rotated tokens
  WITHINGS_REDIRECT_PORT    Auth callback port (default 8765)
  WITHINGS_LOG_LEVEL        error|warn|info|debug (default info)

Register this redirect URI in the Withings developer dashboard:
  http://localhost:8765/callback
`.trim();
  process.stderr.write(text + "\n");
}

async function runAuth(writePath?: string, port?: number): Promise<void> {
  log.info("Starting auth helper", {
    mode: "auth",
    logLevel: getLogLevel(),
    clientIdConfigured: Boolean(process.env.WITHINGS_CLIENT_ID),
    clientSecretConfigured: Boolean(process.env.WITHINGS_CLIENT_SECRET),
    writePath: writePath ?? null,
    port: port ?? Number(process.env.WITHINGS_REDIRECT_PORT ?? 8765),
  });

  const clientId = requireEnv("WITHINGS_CLIENT_ID");
  const clientSecret = requireEnv("WITHINGS_CLIENT_SECRET");

  const tokens = await runOAuthFlow({
    clientId,
    clientSecret,
    redirectPort: port,
  });

  const payload = {
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
    userid: tokens.userid,
    expires_in: tokens.expires_in,
    expires_at: tokens.expires_at,
    scope: tokens.scope,
  };

  if (writePath) {
    const dir = dirname(writePath);
    if (!existsSync(dir) && dir !== ".") {
      mkdirSync(dir, { recursive: true });
    }
    writeFileSync(writePath, JSON.stringify(payload, null, 2), { mode: 0o600 });
    log.info("Wrote tokens to file", { writePath });
    process.stderr.write(`\nTokens written to ${writePath}\n`);
  }

  // Token JSON intentionally on stdout for piping / copy-paste into secrets
  process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
  process.stderr.write(
    "\nCopy refresh_token into WITHINGS_REFRESH_TOKEN (or your MCP catalog secrets).\n",
  );
}

async function main(): Promise<void> {
  const level = (process.env.WITHINGS_LOG_LEVEL ?? "info").toLowerCase();
  if (level === "error" || level === "warn" || level === "info" || level === "debug") {
    setLogLevel(level as LogLevel);
  }

  const { command, writePath, port } = parseArgs(process.argv);

  if (command === "help") {
    printHelp();
    return;
  }

  if (command === "auth") {
    await runAuth(writePath, port);
    return;
  }

  await startMcpServer();
}

main().catch((err) => {
  const fields: Record<string, unknown> = {
    error: err instanceof Error ? err.message : String(err),
  };
  if (getLogLevel() === "debug" && err instanceof Error) {
    fields.stack = err.stack;
  }
  log.error("Fatal error", fields);
  process.exit(1);
});
