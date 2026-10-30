"""FastMCP server assembly."""

from __future__ import annotations

from fastmcp import FastMCP

from withings_mcp import __version__
from withings_mcp.log import get_log_level, log
from withings_mcp.tools.activity import register_activity_tools
from withings_mcp.tools.heart import register_heart_tools
from withings_mcp.tools.measures import register_measure_tools
from withings_mcp.tools.sleep import register_sleep_tools
from withings_mcp.tools.user import register_user_tools
from withings_mcp.withings.client import WithingsClient, create_client_from_env


def create_mcp_server(client: WithingsClient | None = None) -> FastMCP:
    """Build the FastMCP server with all 17 Withings tools."""
    if client is None:
        client = create_client_from_env()

    mcp = FastMCP(
        name="withings-mcp",
        version=__version__,
    )

    register_measure_tools(mcp, client)
    register_activity_tools(mcp, client)
    register_sleep_tools(mcp, client)
    register_heart_tools(mcp, client)
    register_user_tools(mcp, client)

    return mcp


def start_mcp_server() -> None:
    import os

    log.info(
        "Starting Withings MCP server",
        {
            "mode": "mcp",
            "logLevel": get_log_level(),
            "clientIdConfigured": bool(os.environ.get("WITHINGS_CLIENT_ID")),
            "clientSecretConfigured": bool(os.environ.get("WITHINGS_CLIENT_SECRET")),
            "refreshTokenConfigured": bool(os.environ.get("WITHINGS_REFRESH_TOKEN")),
            "tokenFileConfigured": bool(os.environ.get("WITHINGS_TOKEN_FILE")),
        },
    )
    mcp = create_mcp_server()
    log.info("MCP server connected on stdio")
    mcp.run(transport="stdio")
