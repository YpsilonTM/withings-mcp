import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { WithingsClient } from "../withings/client.js";
import { log } from "../log.js";
import { errorResult, textResult } from "./helpers.js";

export function registerUserTools(
  server: McpServer,
  client: WithingsClient,
): void {
  server.registerTool(
    "list_devices",
    {
      description: "List Withings devices paired to the authorized user account.",
    },
    async () => {
      const started = Date.now();
      try {
        log.info("Tool call", { tool: "list_devices" });
        const body = await client.request("/v2/user", { action: "getdevice" });
        const devices = (body as { devices?: unknown[] }).devices ?? [];
        log.info("Tool done", {
          tool: "list_devices",
          durationMs: Date.now() - started,
          count: Array.isArray(devices) ? devices.length : undefined,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "list_devices",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );

  server.registerTool(
    "get_user",
    {
      description: "Get Withings user profile information for the authorized account.",
    },
    async () => {
      const started = Date.now();
      try {
        log.info("Tool call", { tool: "get_user" });
        const body = await client.request("/v2/user", { action: "get" });
        log.info("Tool done", {
          tool: "get_user",
          durationMs: Date.now() - started,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_user",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );

  server.registerTool(
    "get_goals",
    {
      description: "Get user health goals configured in the Withings account.",
    },
    async () => {
      const started = Date.now();
      try {
        log.info("Tool call", { tool: "get_goals" });
        const body = await client.request("/v2/user", { action: "getgoals" });
        log.info("Tool done", {
          tool: "get_goals",
          durationMs: Date.now() - started,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_goals",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );
}
