import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { WithingsClient } from "../withings/client.js";
import { log } from "../log.js";
import { errorResult, resolveUnixRange, textResult } from "./helpers.js";

export function registerHeartTools(
  server: McpServer,
  client: WithingsClient,
): void {
  server.registerTool(
    "list_heart_records",
    {
      description:
        "List ECG / heart recordings (Heart v2 list), including AFib classification metadata. Requires an ECG-capable device (e.g. ScanWatch ECG / BeamO). Often empty if the user only has a scale + non-ECG tracker. Default range: last 30 days. Use get_heart_rate with include_intraday for continuous watch HR instead.",
      inputSchema: {
        startdate: z
          .number()
          .int()
          .optional()
          .describe("Start unix timestamp (seconds). Default: 30 days ago."),
        enddate: z
          .number()
          .int()
          .optional()
          .describe("End unix timestamp (seconds). Default: now."),
        offset: z.number().int().optional().describe("Pagination offset."),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        const { startdate, enddate } = resolveUnixRange({
          ...args,
          defaultHours: 24 * 30,
        });
        log.info("Tool call", {
          tool: "list_heart_records",
          startdate,
          enddate,
          offset: args.offset,
        });
        const body = await client.request("/v2/heart", {
          action: "list",
          startdate,
          enddate,
          offset: args.offset,
        });
        const series = (body as { series?: unknown[] }).series ?? [];
        log.info("Tool done", {
          tool: "list_heart_records",
          durationMs: Date.now() - started,
          count: Array.isArray(series) ? series.length : undefined,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "list_heart_records",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );

  server.registerTool(
    "get_heart_ecg",
    {
      description:
        "Fetch a single ECG waveform/signal by signalid from list_heart_records. Only useful when list_heart_records returned recordings (ECG-capable device). Not for continuous watch heart rate.",
      inputSchema: {
        signalid: z
          .union([z.string(), z.number()])
          .describe("ECG signal id returned by list_heart_records."),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        log.info("Tool call", {
          tool: "get_heart_ecg",
          signalid: String(args.signalid),
        });
        const body = await client.request("/v2/heart", {
          action: "get",
          signalid: args.signalid,
        });
        log.info("Tool done", {
          tool: "get_heart_ecg",
          durationMs: Date.now() - started,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_heart_ecg",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );
}
