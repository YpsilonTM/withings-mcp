/** Shared date helpers and MCP response helpers */

export function nowUnix(): number {
  return Math.floor(Date.now() / 1000);
}

export function hoursAgoUnix(hours: number): number {
  return nowUnix() - Math.floor(hours * 3600);
}

export function daysAgoUnix(days: number): number {
  return nowUnix() - Math.floor(days * 86400);
}

export function toYmd(unix: number): string {
  return new Date(unix * 1000).toISOString().slice(0, 10);
}

export function resolveUnixRange(args: {
  startdate?: number;
  enddate?: number;
  defaultHours?: number;
}): { startdate: number; enddate: number } {
  const enddate = args.enddate ?? nowUnix();
  const startdate =
    args.startdate ?? enddate - Math.floor((args.defaultHours ?? 24) * 3600);
  if (startdate > enddate) {
    throw new Error("startdate must be <= enddate");
  }
  return { startdate, enddate };
}

export function resolveYmdRange(args: {
  startdateymd?: string;
  enddateymd?: string;
  defaultDays?: number;
}): { startdateymd: string; enddateymd: string } {
  const enddateymd = args.enddateymd ?? toYmd(nowUnix());
  const defaultDays = args.defaultDays ?? 7;
  const startdateymd =
    args.startdateymd ?? toYmd(daysAgoUnix(defaultDays - 1));
  return { startdateymd, enddateymd };
}

export function textResult(data: unknown): {
  content: [{ type: "text"; text: string }];
} {
  return {
    content: [
      {
        type: "text",
        text: typeof data === "string" ? data : JSON.stringify(data, null, 2),
      },
    ],
  };
}

export function errorResult(err: unknown): {
  content: [{ type: "text"; text: string }];
  isError: true;
} {
  const message = err instanceof Error ? err.message : String(err);
  return {
    content: [{ type: "text", text: message }],
    isError: true,
  };
}

export const unixDateProps = {
  startdate: {
    type: "number" as const,
    description: "Start of range as unix timestamp (seconds). Defaults to 24h ago.",
  },
  enddate: {
    type: "number" as const,
    description: "End of range as unix timestamp (seconds). Defaults to now.",
  },
};

export const ymdDateProps = {
  startdateymd: {
    type: "string" as const,
    description: "Start date YYYY-MM-DD. Defaults to 7 days ago.",
  },
  enddateymd: {
    type: "string" as const,
    description: "End date YYYY-MM-DD. Defaults to today (UTC).",
  },
};
