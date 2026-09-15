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

const DEFAULT_ACTIVITY_FIELDS =
  "steps,distance,elevation,soft,moderate,intense,active,calories,totalcalories,hr_average,hr_min,hr_max,hr_zone_0,hr_zone_1,hr_zone_2,hr_zone_3";

const DEFAULT_INTRADAY_FIELDS =
  "steps,elevation,calories,distance,heart_rate,spo2_auto,rr,duration,stroke,pool_lap,rmssd,sdnn1,hrv_quality,core_body_temperature,chest_movement_rate";

export function registerActivityTools(
  server: McpServer,
  client: WithingsClient,
): void {
  server.registerTool(
    "get_activity",
    {
      description:
        "Fetch daily activity summaries from the watch/tracker (steps, distance, calories, HR zones, etc.). Prefer this for day-level watch stats; use get_intraday_activity for minute-level series.",
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
          .describe(
            `Comma-separated activity fields. Default: ${DEFAULT_ACTIVITY_FIELDS}`,
          ),
        offset: z.number().int().optional().describe("Pagination offset."),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        const { startdateymd, enddateymd } = resolveYmdRange(args);
        log.info("Tool call", {
          tool: "get_activity",
          startdateymd,
          enddateymd,
        });
        const body = await client.request("/v2/measure", {
          action: "getactivity",
          startdateymd,
          enddateymd,
          data_fields: args.data_fields ?? DEFAULT_ACTIVITY_FIELDS,
          offset: args.offset,
        });
        const activities = (body as { activities?: unknown[] }).activities ?? [];
        log.info("Tool done", {
          tool: "get_activity",
          durationMs: Date.now() - started,
          count: Array.isArray(activities) ? activities.length : undefined,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_activity",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );

  server.registerTool(
    "get_intraday_activity",
    {
      description:
        "Fetch high-resolution watch/tracker series for up to 24 hours: heart_rate, core_body_temperature, spo2_auto, steps, HRV, etc. This is the main source for continuous vitals from a Withings watch (not the scale). Withings returns at most 24 hours per call.",
      inputSchema: {
        startdate: z
          .number()
          .int()
          .optional()
          .describe("Start unix timestamp. Default: 24h ago."),
        enddate: z
          .number()
          .int()
          .optional()
          .describe("End unix timestamp. Default: now."),
        data_fields: z
          .string()
          .optional()
          .describe(
            `Comma-separated fields. Default: ${DEFAULT_INTRADAY_FIELDS}`,
          ),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        let { startdate, enddate } = resolveUnixRange(args);
        const maxSpan = 24 * 3600;
        if (enddate - startdate > maxSpan) {
          log.warn("Intraday window capped to 24h", {
            requestedHours: (enddate - startdate) / 3600,
          });
          startdate = enddate - maxSpan;
        }
        log.info("Tool call", {
          tool: "get_intraday_activity",
          startdate,
          enddate,
        });
        const body = await client.request("/v2/measure", {
          action: "getintradayactivity",
          startdate,
          enddate,
          data_fields: args.data_fields ?? DEFAULT_INTRADAY_FIELDS,
        });
        log.info("Tool done", {
          tool: "get_intraday_activity",
          durationMs: Date.now() - started,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_intraday_activity",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );

  server.registerTool(
    "get_workouts",
    {
      description: "Fetch logged workouts for a date range.",
      inputSchema: {
        startdateymd: z.string().optional().describe("Start date YYYY-MM-DD."),
        enddateymd: z.string().optional().describe("End date YYYY-MM-DD."),
        data_fields: z
          .string()
          .optional()
          .describe(
            "Optional workout data fields (e.g. calories,hr_average,hr_min,hr_max,distance,steps,elevation).",
          ),
        offset: z.number().int().optional(),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        const { startdateymd, enddateymd } = resolveYmdRange(args);
        log.info("Tool call", {
          tool: "get_workouts",
          startdateymd,
          enddateymd,
        });
        const body = await client.request("/v2/measure", {
          action: "getworkouts",
          startdateymd,
          enddateymd,
          data_fields: args.data_fields,
          offset: args.offset,
        });
        const series = (body as { series?: unknown[] }).series ?? [];
        log.info("Tool done", {
          tool: "get_workouts",
          durationMs: Date.now() - started,
          count: Array.isArray(series) ? series.length : undefined,
        });
        return textResult(body);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_workouts",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );
}
