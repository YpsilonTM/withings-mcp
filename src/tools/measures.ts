import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { WithingsClient } from "../withings/client.js";
import { log, getLogLevel } from "../log.js";
import {
  MEASURE_TYPES,
  MEASTYPE_GROUPS,
  decodeMeasureGroups,
  type GetMeasBody,
} from "../withings/types.js";
import {
  errorResult,
  resolveUnixRange,
  textResult,
} from "./helpers.js";

async function getMeas(
  client: WithingsClient,
  meastypes: number[] | undefined,
  startdate: number,
  enddate: number,
  offset?: number,
) {
  const body = await client.request<GetMeasBody>("/measure", {
    action: "getmeas",
    startdate,
    enddate,
    meastypes: meastypes?.length ? meastypes.join(",") : undefined,
    offset,
  });

  const groups = decodeMeasureGroups(body.measuregrps ?? []);
  log.info("Decoded measurements", {
    tool: "get_measurements",
    groupCount: groups.length,
    more: body.more,
    offset: body.offset,
  });

  return {
    updatetime: body.updatetime,
    timezone: body.timezone,
    more: Boolean(body.more),
    offset: body.offset ?? 0,
    count: groups.length,
    measuregrps: groups,
    note: body.more
      ? "More data available; call again with the returned offset."
      : undefined,
  };
}

const rangeSchema = {
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
  offset: z
    .number()
    .int()
    .optional()
    .describe("Pagination offset from a previous more=true response."),
};

export function registerMeasureTools(
  server: McpServer,
  client: WithingsClient,
): void {
  server.registerTool(
    "get_measure_types",
    {
      description:
        "List known Withings measurement type IDs (weight, BP, SpO2, temperature, etc.). No API call.",
    },
    async () => {
      log.info("Tool call", { tool: "get_measure_types" });
      return textResult({
        types: Object.entries(MEASURE_TYPES).map(([id, meta]) => ({
          type: Number(id),
          ...meta,
        })),
        groups: MEASTYPE_GROUPS,
      });
    },
  );

  server.registerTool(
    "get_measurements",
    {
      description:
        "Fetch Withings health measurements (getmeas). Optionally filter by meastypes. Values are decoded (value * 10^unit).",
      inputSchema: {
        ...rangeSchema,
        meastypes: z
          .array(z.number().int())
          .optional()
          .describe(
            "Measurement type IDs to include. Omit for all. Use get_measure_types for the catalog.",
          ),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        const { startdate, enddate } = resolveUnixRange(args);
        log.info("Tool call", {
          tool: "get_measurements",
          startdate,
          enddate,
          meastypes: args.meastypes,
          offset: args.offset,
        });
        const data = await getMeas(
          client,
          args.meastypes,
          startdate,
          enddate,
          args.offset,
        );
        log.info("Tool done", {
          tool: "get_measurements",
          durationMs: Date.now() - started,
          count: data.count,
        });
        return textResult(data);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_measurements",
          error: e instanceof Error ? e.message : String(e),
          ...(getLogLevel() === "debug" && e instanceof Error
            ? { stack: e.stack }
            : {}),
        });
        return errorResult(e);
      }
    },
  );

  const makeTypedTool = (
    name: string,
    description: string,
    meastypes: number[],
  ) => {
    server.registerTool(
      name,
      {
        description,
        inputSchema: rangeSchema,
      },
      async (args) => {
        const started = Date.now();
        try {
          const { startdate, enddate } = resolveUnixRange(args);
          log.info("Tool call", {
            tool: name,
            startdate,
            enddate,
            meastypes,
            offset: args.offset,
          });
          const data = await getMeas(
            client,
            meastypes,
            startdate,
            enddate,
            args.offset,
          );
          log.info("Tool done", {
            tool: name,
            durationMs: Date.now() - started,
            count: data.count,
          });
          return textResult(data);
        } catch (e) {
          log.error("Tool failed", {
            tool: name,
            error: e instanceof Error ? e.message : String(e),
          });
          return errorResult(e);
        }
      },
    );
  };

  makeTypedTool(
    "get_weight",
    "Fetch scale weight measurements (meastype 1). Typical source: Withings scale.",
    [...MEASTYPE_GROUPS.weight],
  );
  makeTypedTool(
    "get_body_composition",
    "Fetch scale body composition: fat free mass, fat ratio, fat mass, muscle, hydration, bone (types 5,6,8,76,77,88). Typical source: Withings scale.",
    [...MEASTYPE_GROUPS.body_composition],
  );
  makeTypedTool(
    "get_blood_pressure",
    "Fetch blood pressure and related spot pulse (diastolic 9, systolic 10, heart rate 11). Typical source: BPM or scale, not continuous watch HR.",
    [...MEASTYPE_GROUPS.blood_pressure],
  );
  makeTypedTool(
    "get_spo2",
    "Fetch spot SpO2 measurements (meastype 54) from getmeas. For continuous watch SpO2, prefer get_intraday_activity with spo2_auto.",
    [...MEASTYPE_GROUPS.spo2],
  );

  server.registerTool(
    "get_body_temperature",
    {
      description:
        "Fetch body temperature. Spot readings (meastypes 12/71/73 via getmeas) come from thermometers or occasional device measures. For Withings watches, set include_intraday=true to fetch continuous core_body_temperature (max 24h window) — that is usually where watch temp lives.",
      inputSchema: {
        ...rangeSchema,
        include_intraday: z
          .boolean()
          .optional()
          .describe(
            "If true, also fetch watch intraday core_body_temperature via getintradayactivity (capped to 24h). Recommended for ScanWatch / activity trackers.",
          ),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        let { startdate, enddate } = resolveUnixRange(args);
        log.info("Tool call", {
          tool: "get_body_temperature",
          startdate,
          enddate,
          include_intraday: args.include_intraday ?? false,
        });

        const spot = await getMeas(
          client,
          [...MEASTYPE_GROUPS.body_temperature],
          startdate,
          enddate,
          args.offset,
        );

        let intraday: unknown = undefined;
        if (args.include_intraday) {
          const maxSpan = 24 * 3600;
          if (enddate - startdate > maxSpan) {
            startdate = enddate - maxSpan;
            log.warn("Intraday temperature window capped to 24h", {
              startdate,
              enddate,
            });
          }
          intraday = await client.request("/v2/measure", {
            action: "getintradayactivity",
            startdate,
            enddate,
            data_fields: "core_body_temperature",
          });
        }

        const result = {
          spot_measurements: spot,
          intraday: intraday ?? null,
        };
        log.info("Tool done", {
          tool: "get_body_temperature",
          durationMs: Date.now() - started,
          spotCount: spot.count,
          include_intraday: Boolean(args.include_intraday),
        });
        return textResult(result);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_body_temperature",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );

  server.registerTool(
    "get_heart_rate",
    {
      description:
        "Fetch heart rate. Spot readings (meastype 11 via getmeas) come from scale/BPM when you take a measurement. For Withings watches, set include_intraday=true (or use get_intraday_activity) for continuous HR — that is usually where watch HR lives (max 24h window).",
      inputSchema: {
        ...rangeSchema,
        include_intraday: z
          .boolean()
          .optional()
          .describe(
            "If true, also fetch continuous watch heart_rate via getintradayactivity (capped to 24h). Recommended for ScanWatch / activity trackers.",
          ),
      },
    },
    async (args) => {
      const started = Date.now();
      try {
        let { startdate, enddate } = resolveUnixRange(args);
        log.info("Tool call", {
          tool: "get_heart_rate",
          startdate,
          enddate,
          include_intraday: args.include_intraday ?? false,
        });

        const spot = await getMeas(
          client,
          [...MEASTYPE_GROUPS.heart_rate],
          startdate,
          enddate,
          args.offset,
        );

        let intraday: unknown = undefined;
        if (args.include_intraday) {
          const maxSpan = 24 * 3600;
          if (enddate - startdate > maxSpan) {
            startdate = enddate - maxSpan;
            log.warn("Intraday HR window capped to 24h", { startdate, enddate });
          }
          intraday = await client.request("/v2/measure", {
            action: "getintradayactivity",
            startdate,
            enddate,
            data_fields: "heart_rate",
          });
        }

        const result = {
          spot_measurements: spot,
          intraday: intraday ?? null,
        };
        log.info("Tool done", {
          tool: "get_heart_rate",
          durationMs: Date.now() - started,
          spotCount: spot.count,
          include_intraday: Boolean(args.include_intraday),
        });
        return textResult(result);
      } catch (e) {
        log.error("Tool failed", {
          tool: "get_heart_rate",
          error: e instanceof Error ? e.message : String(e),
        });
        return errorResult(e);
      }
    },
  );
}
