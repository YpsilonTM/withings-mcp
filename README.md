# Withings MCP Server

Model Context Protocol (MCP) server for the [Withings Public API](https://developer.withings.com/). Query weight, body composition, heart rate, core body temperature, SpO2, activity, sleep, workouts, and ECG recordings from AI clients (Cursor, Claude Desktop, Docker MCP Gateway, etc.).

## Features

- **stdio MCP server** — works with Docker MCP Gateway / Toolkit catalogs
- **One-shot `auth` helper** — browser OAuth, prints tokens (no always-on auth service)
- **Broad tool set** — scale measurements, watch/intraday vitals, sleep, heart/ECG, devices & goals
- **Token refresh** — automatic access-token refresh; optional file to persist rotated refresh tokens
- **Structured stderr logging** — JSON lines, safe for MCP (stdout stays protocol-only)

## Scale vs watch (important)

Withings splits data by **how** it was recorded. Empty tool results usually mean you queried the wrong path for that device.

| Device | Typical data | Prefer these tools |
|--------|----------------|--------------------|
| **Scale** | Weight, body composition, occasional spot pulse | `get_weight`, `get_body_composition`, `get_measurements` |
| **Watch / activity tracker** | Continuous HR, **core body temperature**, SpO2, steps | `get_intraday_activity`, or `get_heart_rate` / `get_body_temperature` with `include_intraday: true`; daily rollups via `get_activity` |
| **Sleep mat / analyzer** (if you have one) | Night summaries & series | `get_sleep_summary`, `get_sleep` |
| **BPM** (if you have one) | Spot blood pressure | `get_blood_pressure` |

**Spot vs intraday**

- **Spot** (`getmeas` / tools without `include_intraday`) — discrete measurements when you step on the scale or take a reading. Often empty for watch-only vitals.
- **Intraday** (`getintradayactivity`, max **24h** per call) — time series from the watch while you wear it. This is where continuous HR and `core_body_temperature` live.

Example: “body temp last 24h” from a ScanWatch → use `get_body_temperature` with `include_intraday: true` (or `get_intraday_activity` with `data_fields=core_body_temperature`), not spot-only temperature types.

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

With Docker (recommended):

```bash
docker run --rm -p 8765:8765 \
  -e WITHINGS_CLIENT_ID=your_client_id \
  -e WITHINGS_CLIENT_SECRET=your_client_secret \
  ghcr.io/<owner>/withings-mcp:latest auth
```

Or from source:

```bash
npm ci && npm run build
WITHINGS_CLIENT_ID=... WITHINGS_CLIENT_SECRET=... node dist/index.js auth
```

1. Open the printed authorize URL in your browser
2. Log in to Withings and accept
3. Copy `refresh_token` from the JSON printed on stdout

Optional: write tokens to a file:

```bash
... auth --write ./tokens.json
```

### 3. Run the MCP server

```bash
docker run -i --rm \
  -e WITHINGS_CLIENT_ID=your_client_id \
  -e WITHINGS_CLIENT_SECRET=your_client_secret \
  -e WITHINGS_REFRESH_TOKEN=your_refresh_token \
  -e WITHINGS_LOG_LEVEL=info \
  ghcr.io/<owner>/withings-mcp:latest
```

`-i` is required so the client can speak MCP over stdin/stdout.

## Docker MCP Gateway catalog

Add an entry like [`examples/catalog-entry.yaml`](examples/catalog-entry.yaml) to your gateway `catalog.yaml`, then put secrets in `secrets.env`:

```env
WITHINGS_CLIENT_ID=...
WITHINGS_CLIENT_SECRET=...
WITHINGS_REFRESH_TOKEN=...
```

**Required for long-lived deployments:** mount a writable volume and set `WITHINGS_TOKEN_FILE=/data/tokens.json` so rotated refresh tokens survive container restarts. Withings rotates refresh tokens on every refresh; without a writable store, auth will break after ~8 hours when the gateway starts a fresh container.

Example volume (homeserver): `/home/ypsilon/data/withings:/data`

If your GHCR package is private and the gateway host cannot pull it, either grant the host a token with `read:packages`, or build the image on the host from this repo and keep `--pull never` (Docker MCP Gateway does this when the image is already local).

## Cursor / Claude Desktop

See [`examples/cursor-mcp.json`](examples/cursor-mcp.json) for a Docker-based `mcpServers` snippet.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `WITHINGS_CLIENT_ID` | Yes | OAuth client ID |
| `WITHINGS_CLIENT_SECRET` | Yes | OAuth client secret |
| `WITHINGS_REFRESH_TOKEN` | Yes (MCP) | Refresh token from `auth` (or provide via `WITHINGS_TOKEN_FILE`) |
| `WITHINGS_TOKEN_FILE` | No | Path to persist tokens (default `/data/tokens.json` if `/data` exists) |
| `WITHINGS_REDIRECT_PORT` | No | Auth callback port (default `8765`) |
| `WITHINGS_LOG_LEVEL` | No | `error` \| `warn` \| `info` \| `debug` (default `info`) |

OAuth scopes requested: `user.info`, `user.metrics`, `user.activity`, `user.sleepevents`.

## Tools

| Tool | Best for | Notes |
|------|----------|--------|
| `get_measure_types` | Reference | Static meastype catalog |
| `get_measurements` | Scale / spot metrics | Filter with `meastypes`; not continuous watch vitals |
| `get_weight` | Scale | Weight (type 1) |
| `get_body_composition` | Scale | Fat, muscle, bone, hydration |
| `get_blood_pressure` | BPM / scale spot | Systolic / diastolic / pulse |
| `get_heart_rate` | Watch (intraday) or spot | Use `include_intraday: true` for continuous watch HR |
| `get_body_temperature` | Watch (intraday) or spot | Use `include_intraday: true` for watch `core_body_temperature` |
| `get_spo2` | Spot SpO2 | Continuous watch SpO2 → `get_intraday_activity` (`spo2_auto`) |
| `get_activity` | Watch daily totals | Steps, calories, HR zones |
| `get_intraday_activity` | Watch continuous vitals | HR, temp, SpO2, steps; **≤24h** per call |
| `get_workouts` | Watch workouts | Logged sessions |
| `get_sleep_summary` | Sleep device / watch nights | Per-night summaries (default 7 days) |
| `get_sleep` | Sleep series | High-frequency stages / vitals (default 24h) |
| `list_heart_records` | ECG devices | Often empty without ECG hardware |
| `get_heart_ecg` | ECG devices | Single signal by `signalid` |
| `list_devices` | Account | Paired devices |
| `get_goals` | Account | Goals |

Example prompts:

- “What was my heart rate in the last 24 hours?” → watch intraday HR
- “Show my core body temperature today.” → watch intraday temp
- “What did I weigh this morning?” → scale weight
- “How did I sleep the last 7 nights?” → sleep summary

## Logging

All logs go to **stderr** as one JSON object per line so they appear in `docker logs` / MCP Gateway without breaking the MCP session on stdout.

```bash
# More detail while debugging auth or API errors
-e WITHINGS_LOG_LEVEL=debug
```

Logged at `info`: startup config (booleans only), tool name + date range, Withings status, durations.  
Never logged: access/refresh tokens, client secret, Authorization headers.

## Rate limits

Withings asks partners not to poll more often than about once every 10 minutes per user for sync-style usage. Prefer explicit date ranges when asking the model for historical data.

## Development

```bash
npm ci
npm run build
npm run auth          # tsx auth helper
npm start             # MCP on stdio (needs env vars)
```

Build the image locally:

```bash
docker build -t withings-mcp:local .
docker run --rm -p 8765:8765 \
  -e WITHINGS_CLIENT_ID -e WITHINGS_CLIENT_SECRET \
  withings-mcp:local auth
```

Images are published to GHCR on pushes to `main` and version tags `v*` via GitHub Actions.

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Auth callback never completes | Confirm redirect URI is exactly `http://localhost:8765/callback`; port `8765` free; use `-p 8765:8765` with Docker |
| `status=343` / invalid token | Refresh token expired or revoked — re-run `auth` and update secrets |
| `status=601` | Rate limited — back off |
| Empty weight/composition | No scale sync in range |
| Empty HR/temp without intraday | Watch data is usually intraday — set `include_intraday: true` or call `get_intraday_activity` |
| Empty data (`status=100`) | No measurements in range, or device never synced that metric |
| MCP client hangs / protocol errors | Ensure nothing else writes to stdout; set `WITHINGS_LOG_LEVEL=debug` and inspect **stderr** / container logs |

## License

MIT — see [LICENSE](LICENSE).

## Disclaimer

This project is not affiliated with Withings. Use only with accounts and data you are authorized to access. Health data is sensitive — store secrets and token files securely.
