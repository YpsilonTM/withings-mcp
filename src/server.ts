import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { createClientFromEnv } from "./withings/client.js";
import { log, getLogLevel } from "./log.js";
import { registerMeasureTools } from "./tools/measures.js";
import { registerActivityTools } from "./tools/activity.js";
import { registerSleepTools } from "./tools/sleep.js";
import { registerHeartTools } from "./tools/heart.js";
import { registerUserTools } from "./tools/user.js";

export async function startMcpServer(): Promise<void> {
  log.info("Starting Withings MCP server", {
    mode: "mcp",
    logLevel: getLogLevel(),
    clientIdConfigured: Boolean(process.env.WITHINGS_CLIENT_ID),
    clientSecretConfigured: Boolean(process.env.WITHINGS_CLIENT_SECRET),
    refreshTokenConfigured: Boolean(process.env.WITHINGS_REFRESH_TOKEN),
    tokenFileConfigured: Boolean(process.env.WITHINGS_TOKEN_FILE),
  });

  const client = createClientFromEnv();
  const server = new McpServer({
    name: "withings-mcp",
    version: "1.0.0",
  });

  registerMeasureTools(server, client);
  registerActivityTools(server, client);
  registerSleepTools(server, client);
  registerHeartTools(server, client);
  registerUserTools(server, client);

  const transport = new StdioServerTransport();
  await server.connect(transport);
  log.info("MCP server connected on stdio");
}
