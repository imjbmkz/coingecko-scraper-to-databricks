# CoinGecko to Databricks Volume

This Python job fetches the raw JSON bytes from Bitcoin's 1-day market-chart and
OHLC endpoints and uploads each response directly to a Unity Catalog Volume. It
does not create local temporary JSON files.

Files are append-only and named like:

```text
/Volumes/main/default/coingecko_raw/coingecko/bitcoin/market_chart_20260819T...Z.json
/Volumes/main/default/coingecko_raw/coingecko/bitcoin/ohlc_20260819T...Z.json
```

## Databricks configuration

Create or choose a Unity Catalog Volume, then provide these secrets/environment
variables:

- `DATABRICKS_HOST`: workspace URL, with no trailing slash.
- `DATABRICKS_TOKEN`: a PAT for this short demo. Store it only as a hosting
  secret. For longer-lived automation, use a service principal with OAuth.
- `DATABRICKS_VOLUME_PATH`: `/Volumes/<catalog>/<schema>/<volume>`.
- `DATABRICKS_TARGET_DIR` (optional): folder within the volume; defaults to
  `coingecko/bitcoin`.

The Databricks identity needs `USE CATALOG`, `USE SCHEMA`, and `WRITE VOLUME` on
the chosen objects. The workspace must support Unity Catalog Volumes and Files
API access. Never commit the token or `.env` file.

## Run locally

Python 3.11+ is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your values; the application loads it automatically.
python run.py
```

## Free hourly scheduling (recommended for this demo)

The included GitHub Actions workflow runs at minute 17 every hour and can also
be started manually. Add `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, and
`DATABRICKS_VOLUME_PATH` under repository **Settings > Secrets and variables >
Actions**, push the repository, then manually run it once to verify access.

GitHub schedules can be delayed during high load, so this is suitable for a
demo ingestion rather than a time-critical production pipeline. Disable the
workflow after Friday and revoke the demo token.

## Vercel and PythonAnywhere

- **Vercel Hobby:** not suitable for native hourly scheduling; Hobby cron is
  limited to once per day. `api/cron.py` is included if you want an external
  scheduler to invoke a Vercel Python Function. Set all Databricks variables and
  `CRON_SECRET`, then call `/api/cron` with `Authorization: Bearer <secret>`.
- **PythonAnywhere free:** not suitable for a new account's hourly tasks. Paid
  accounts support hourly scheduled tasks; free scheduled-task availability is
  restricted and, where available for older accounts, is daily.
- **GitHub Actions:** best fit here: hourly scheduling, secrets, no persistent
  server, and enough included usage for a lightweight job that runs only until
  Friday.

## CoinGecko authentication and operational notes

CoinGecko currently lists these endpoints in its keyless public API, so the job
sends no API key. Keyless traffic is rate-limited and availability is not
guaranteed; the HTTP client retries transient errors and honors `Retry-After`.
Each run performs two CoinGecko requests and creates two timestamped raw files.
