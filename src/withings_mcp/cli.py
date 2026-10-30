"""CLI entry point: MCP server (default) or one-shot OAuth auth helper."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from withings_mcp.auth.oauth import run_oauth_flow
from withings_mcp.log import LogLevel, get_log_level, log, set_log_level
from withings_mcp.withings.client import require_env


def _load_dotenv() -> None:
    """Load .env from cwd if present; does not override already-set env vars."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)


def _configure_logging() -> None:
    level = (os.environ.get("WITHINGS_LOG_LEVEL") or "info").lower()
    if level in ("error", "warn", "info", "debug"):
        set_log_level(level)  # type: ignore[arg-type]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="withings-mcp",
        description="Withings Model Context Protocol server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment:\n"
            "  WITHINGS_CLIENT_ID        Required\n"
            "  WITHINGS_CLIENT_SECRET    Required\n"
            "  WITHINGS_REFRESH_TOKEN    Required for MCP (from auth)\n"
            "  WITHINGS_TOKEN_FILE       Optional path to persist rotated tokens\n"
            "  WITHINGS_REDIRECT_PORT    Auth callback port (default 8765)\n"
            "  WITHINGS_LOG_LEVEL        error|warn|info|debug (default info)\n"
            "\n"
            "Register this redirect URI in the Withings developer dashboard:\n"
            "  http://localhost:8765/callback\n"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    auth = sub.add_parser(
        "auth",
        help="Run one-time OAuth and print tokens as JSON",
        description=(
            "Start a local callback server, open/print the Withings authorize URL, "
            "exchange the code, and print tokens as JSON on stdout."
        ),
    )
    auth.add_argument(
        "--write",
        metavar="PATH",
        help="Optionally write tokens JSON to PATH",
    )
    auth.add_argument(
        "--port",
        type=int,
        default=None,
        help="OAuth callback port (default: WITHINGS_REDIRECT_PORT or 8765)",
    )
    return parser


def run_auth(*, write_path: str | None = None, port: int | None = None) -> None:
    log.info(
        "Starting auth helper",
        {
            "mode": "auth",
            "logLevel": get_log_level(),
            "clientIdConfigured": bool(os.environ.get("WITHINGS_CLIENT_ID")),
            "clientSecretConfigured": bool(os.environ.get("WITHINGS_CLIENT_SECRET")),
            "writePath": write_path,
            "port": port
            if port is not None
            else int(os.environ.get("WITHINGS_REDIRECT_PORT") or 8765),
        },
    )

    client_id = require_env("WITHINGS_CLIENT_ID")
    client_secret = require_env("WITHINGS_CLIENT_SECRET")

    tokens = run_oauth_flow(
        client_id=client_id,
        client_secret=client_secret,
        redirect_port=port,
    )

    payload = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "userid": tokens.get("userid"),
        "expires_in": tokens.get("expires_in"),
        "expires_at": tokens.get("expires_at"),
        "scope": tokens.get("scope"),
    }

    if write_path:
        path = Path(write_path)
        if path.parent != Path(".") and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write for auth --write as well
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        log.info("Wrote tokens to file", {"writePath": write_path})
        sys.stderr.write(f"\nTokens written to {write_path}\n")

    # Token JSON intentionally on stdout for piping / copy-paste into secrets
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    sys.stderr.write(
        "\nCopy refresh_token into WITHINGS_REFRESH_TOKEN "
        "(or your MCP catalog secrets / token file).\n"
    )


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    _configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "auth":
            run_auth(write_path=args.write, port=args.port)
            return

        # Default: MCP server on stdio
        from withings_mcp.server import start_mcp_server

        start_mcp_server()
    except SystemExit:
        raise
    except Exception as err:
        fields: dict[str, object] = {"error": str(err)}
        if get_log_level() == "debug":
            fields["exc_type"] = type(err).__name__
        log.error("Fatal error", fields)
        sys.exit(1)


# Re-export for typing convenience
__all__ = ["main", "build_parser", "run_auth", "LogLevel"]
