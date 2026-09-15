import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { WithingsClient } from "../withings/client.js";
import { log } from "../log.js";
import {
  errorResult,
  resolveUnixRange,
  resolveYmdRange,
  textResult,
} from "./helpers.js";

const DEFAULT_SUMMARY_FIELDS =
  "nb_rem_episodes,sleep_score,snoring,snoringepisodecount,sleep_efficiency,asleepduration,deepsleepduration,lightsleepduration,remsleepduration,durationtosleep,durationtowakeup,out_of_bed_count,hr_average,hr_min,hr_max,rr_average,rr_min,rr_max,breathing_disturbances_intensity,total_timeinbed,total_sleep_time";

const DEFAULT_SERIES_FIELDS =
  "hr,rr,snoring,sdnn_1,rmssd,hrv_quality,mvt_score,chest_movement_rate";

export function registerSleepTools(
  server: McpServer,
  client: WithingsClient,
): void {
  server.registerTool(
    "get_sleep_summary",
    {
      description:
        "Fetch per-night sleep summaries (score, stages, HR/RR stats, snoring, etc.). Default range is the last 7 days. Typical sources: Sleep Analyzer / Sleep Mat, or watch sleep tracking. For minute-level detail within a night, use get_sleep.",
      inputSchema: {
        startdateymd: z
          .string()
          .optional()
          .describe("Start date YYYY-MM-DD. Default: 7 days ago."),
        enddateymd: z
          .string()
          .optional()
          .describe("End date YYYY-MM-DD. Default: today UTC."),
        data_fields: z
          .string()
          .optional()
          .describe(`Comma-separated fields. Default includes score, stages, HR/RR.`),
        lastupdate: z
          .number()
          .int()
          .optional()
          .describe(
            "Only return nights updated after this unix timestamp. When set, date range params are omitted.",
          ),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        const { startdateymd, enddateymd } = resolveYmdRange(args);
        log.info("Tool call", {
          tool: "get_sleep_summary",
          startdateymd,
          enddateymd,
          lastupdate: args.lastupdate,
        });
        const body = await client.request("/v2/sleep", {
          action: "getsummary",
          startdateymd: args.lastupdate != null ? undefined : startdateymd,
          enddateymd: args.lastupdate != null ? undefined : enddateymd,
          data_fields: args.data_fields ?? DEFAULT_SUMMARY_FIELDS,
          lastupdate: args.lastupdate,
        });
        const series = (body as { series?: unknown[] }).series ?? [];
        log.info("Tool done", {
          tool: "get_sleep_summary",
          durationMs: Date.now() - started,
          count: Array.isArray(series) ? series.length : undefined,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_sleep_summary",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );

  server.registerTool(
    "get_sleep",
    {
      description:
        "Fetch high-frequency sleep stage and vital series for a time window (Sleep get): stages, HR, respiration, snoring, HRV, etc. Default range is the last 24 hours. Prefer get_sleep_summary for multi-night overviews; use this for detailed series within a night. Typical sources: Sleep Analyzer / Sleep Mat, or watch sleep tracking.",
      inputSchema: {
        startdate: z
          .number()
          .int()
          .optional()
          .describe("Start unix timestamp (seconds). Default: 24h ago."),
        enddate: z
          .number()
          .int()
          .optional()
          .describe("End unix timestamp (seconds). Default: now."),
        data_fields: z
          .string()
          .optional()
          .describe(`Comma-separated series fields. Default: ${DEFAULT_SERIES_FIELDS}`),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        // Sleep series is typically one night; default last 24h
        const { startdate, enddate } = resolveUnixRange({
          ...args,
          defaultHours: 24,
        });
        log.info("Tool call", { tool: "get_sleep", startdate, enddate });
        const body = await client.request("/v2/sleep", {
          action: "get",
          startdate,
          enddate,
          data_fields: args.data_fields ?? DEFAULT_SERIES_FIELDS,
        });
        const series = (body as { series?: unknown[] }).series ?? [];
        log.info("Tool done", {
          tool: "get_sleep",
          durationMs: Date.now() - started,
          count: Array.isArray(series) ? series.length : undefined,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_sleep",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );
}
