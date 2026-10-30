# Withings MCP Server

Model Context Protocol (MCP) server for the [Withings Public API](https://developer.withings.com/). Query weight, body composition, heart rate, core body temperature, SpO2, activity, sleep, workouts, and ECG recordings from AI clients (Cursor, Claude Desktop, MCPHub, etc.).

Python / **stdio** / run via **`uvx`** — no Docker image required.

## Features

- **stdio MCP server** — works with Cursor, Claude Desktop, MCPHub, and other MCP clients
- **One-shot `auth` helper** — browser OAuth, prints tokens (no always-on auth service)
- **Broad tool set** — scale measurements, watch/intraday vitals, sleep, heart/ECG, devices & goals
- **Token refresh** — automatic access-token refresh with **atomic** persistence of rotated refresh tokens
- **Structured stderr logging** — JSON lines, safe for MCP (stdout stays protocol-only)

## Scale vs watch (important)

Withings splits data by **how** it was recorded. Empty tool results usually mean you queried the wrong path for that device.

| Device | Typical data | Prefer these tools |
|--------|----------------|--------------------|
| **Scale** | Weight, body composition, occasional spot pulse | `withings_get_weight`, `withings_get_body_composition`, `withings_get_measurements` |
| **Watch / activity tracker** | Continuous HR, **core body temperature**, SpO2, steps | `withings_get_intraday_activity`, or `withings_get_heart_rate` / `withings_get_body_temperature` with `include_intraday: true`; daily rollups via `withings_get_activity` |
| **Sleep mat / analyzer** (if you have one) | Night summaries & series | `withings_get_sleep_summary`, `withings_get_sleep` |
| **BPM** (if you have one) | Spot blood pressure | `withings_get_blood_pressure` |

**Spot vs intraday**

- **Spot** (`getmeas` / tools without `include_intraday`) — discrete measurements when you step on the scale or take a reading. Often empty for watch-only vitals.
- **Intraday** (`getintradayactivity`, max **24h** per API call) — time series from the watch while you wear it. This is where continuous HR and `core_body_temperature` live. Ranges longer than 24h are split into consecutive windows automatically.

Example: “body temp last 24h” from a ScanWatch → use `withings_get_body_temperature` with `include_intraday: true` (or `withings_get_intraday_activity` with `data_fields=core_body_temperature`), not spot-only temperature types.

## Quick start

### 1. Create a Withings developer app

1. Open [developer.withings.com/dashboard](https://developer.withings.com/dashboard/)
2. Create an application
3. Note **Client ID** and **Client Secret**
4. Register this redirect URI exactly:

```text
http://localhost:8765/callback
```

### 2. Obtain a refresh token (one time)

```bash
uvx --from git+https://github.com/YpsilonTM/withings-mcp withings-mcp auth \
  --write ./tokens.json
```

Or from a local checkout:

```bash
uv sync
uv run withings-mcp auth --write ./tokens.json
```

Set `WITHINGS_CLIENT_ID` and `WITHINGS_CLIENT_SECRET` in the environment (or a `.env` your shell loads) before running `auth`.

1. Open the printed authorize URL in your browser
2. Log in to Withings and accept
3. Tokens are printed as JSON on stdout; with `--write`, also saved to the given path

### 3. Run the MCP server

```bash
export WITHINGS_CLIENT_ID=...
export WITHINGS_CLIENT_SECRET=...
export WITHINGS_TOKEN_FILE=./tokens.json   # or WITHINGS_REFRESH_TOKEN=...

uvx --from git+https://github.com/YpsilonTM/withings-mcp withings-mcp
```

## MCPHub / Cursor

### MCPHub `mcp_settings.json`

```json
{
  "mcpServers": {
    "withings": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/YpsilonTM/withings-mcp",
        "withings-mcp"
      ],
      "env": {
        "WITHINGS_CLIENT_ID": "",
        "WITHINGS_CLIENT_SECRET": "",
        "WITHINGS_REFRESH_TOKEN": "",
        "WITHINGS_TOKEN_FILE": "/data/withings/tokens.json",
        "WITHINGS_LOG_LEVEL": "info"
      }
    }
  }
}
```

Bind secrets via MCPHub per-user credentials rather than hard-coding them. The token file path must be mounted into the MCPHub container (Withings **rotates** the refresh token on every refresh; without a writable mount, auth breaks after the first refresh).

See also [`examples/mcp_settings.json`](examples/mcp_settings.json).

### Cursor / Claude Desktop

```json
{
  "mcpServers": {
    "withings": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/YpsilonTM/withings-mcp",
        "withings-mcp"
      ],
      "env": {
        "WITHINGS_CLIENT_ID": "your_client_id",
        "WITHINGS_CLIENT_SECRET": "your_client_secret",
        "WITHINGS_TOKEN_FILE": "/absolute/path/to/tokens.json"
      }
    }
  }
}
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WITHINGS_CLIENT_ID` | Yes | OAuth client ID |
| `WITHINGS_CLIENT_SECRET` | Yes | OAuth client secret |
| `WITHINGS_REFRESH_TOKEN` | Yes (MCP)* | Refresh token from `auth` (*or provide via `WITHINGS_TOKEN_FILE`) |
| `WITHINGS_TOKEN_FILE` | No | Path to persist tokens (default `/data/tokens.json` if `/data` exists) |
| `WITHINGS_REDIRECT_PORT` | No | Auth callback port (default `8765`) |
| `WITHINGS_LOG_LEVEL` | No | `error` \| `warn` \| `info` \| `debug` (default `info`) |

OAuth scopes requested: `user.info`, `user.metrics`, `user.activity`, `user.sleepevents`.

## Tools

| Tool | Best for | Notes |
|------|----------|--------|
| `withings_get_measure_types` | Reference | Static meastype catalog |
| `withings_get_measurements` | Scale / spot metrics | Filter with `meastypes`; not continuous watch vitals |
| `withings_get_weight` | Scale | Weight (type 1) |
| `withings_get_body_composition` | Scale | Fat, muscle, bone, hydration |
| `withings_get_blood_pressure` | BPM / scale spot | Systolic / diastolic / pulse |
| `withings_get_heart_rate` | Watch (intraday) or spot | Use `include_intraday: true` for continuous watch HR |
| `withings_get_body_temperature` | Watch (intraday) or spot | Use `include_intraday: true` for watch `core_body_temperature` |
| `withings_get_spo2` | Spot SpO2 | Continuous watch SpO2 → `withings_get_intraday_activity` (`spo2_auto`) |
| `withings_get_activity` | Watch daily totals | Steps, calories, HR zones |
| `withings_get_intraday_activity` | Watch continuous vitals | HR, temp, SpO2, steps; **≤24h** per API call (auto-split) |
| `withings_get_workouts` | Watch workouts | Logged sessions |
| `withings_get_sleep_summary` | Sleep device / watch nights | Per-night summaries (default 7 days) |
| `withings_get_sleep` | Sleep series | High-frequency stages / vitals (default 24h) |
| `withings_list_heart_records` | ECG devices | Often empty without ECG hardware |
| `withings_get_heart_ecg` | ECG devices | Single signal by `signalid` |
| `withings_list_devices` | Account | Paired devices |
| `withings_get_goals` | Account | Goals |

Example prompts:

- “What was my heart rate in the last 24 hours?” → watch intraday HR
- “Show my core body temperature today.” → watch intraday temp
- “What did I weigh this morning?” → scale weight
- “How did I sleep the last 7 nights?” → sleep summary

## Logging

All logs go to **stderr** as one JSON object per line so they never break the MCP session on stdout.

```bash
WITHINGS_LOG_LEVEL=debug uv run withings-mcp
```

Logged at `info`: startup config (booleans only), tool name + date range, Withings status, durations.  
Never logged: access/refresh tokens, client secret, Authorization headers.

## Rate limits

Withings asks partners not to poll more often than about once every 10 minutes per user for sync-style usage. Prefer explicit date ranges when asking the model for historical data. API `status=601` is surfaced as a rate-limit error.

## Development

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run withings-mcp --help
uv run withings-mcp auth --help
uv run ruff check src tests
uv run pytest
```

MCP Inspector:

```bash
npx @modelcontextprotocol/inspector uv run withings-mcp
```

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Auth callback never completes | Confirm redirect URI is exactly `http://localhost:8765/callback`; port `8765` free |
| `status=343` / invalid token | Refresh token expired or revoked — re-run `withings-mcp auth` and update secrets / token file |
| `status=601` | Rate limited — back off |
| Empty weight/composition | No scale sync in range |
| Empty HR/temp without intraday | Watch data is usually intraday — set `include_intraday: true` or call `withings_get_intraday_activity` |
| Empty data (`status=100`) | No measurements in range, or device never synced that metric |
| MCP client hangs / protocol errors | Ensure nothing else writes to stdout; set `WITHINGS_LOG_LEVEL=debug` and inspect **stderr** |
| Auth breaks after ~hours | Token file not writable / not mounted — set `WITHINGS_TOKEN_FILE` on a persistent path |

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is not affiliated with Withings. Use only with accounts and data you are authorized to access. Health data is sensitive — store secrets and token files securely.
