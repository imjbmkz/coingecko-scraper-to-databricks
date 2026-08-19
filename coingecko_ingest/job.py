"""Fetch CoinGecko JSON responses and upload them to a Databricks Volume."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
ENDPOINTS: Mapping[str, str] = {
    "market_chart": "/coins/{coin_id}/market_chart",
    "ohlc": "/coins/{coin_id}/ohlc",
}
REQUEST_PARAMETERS: Mapping[str, str] = {"vs_currency": "usd", "days": "1"}
COIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
DEFAULT_COINS_FILE = Path(__file__).resolve().parent.parent / "coins.txt"


@dataclass(frozen=True)
class Settings:
    databricks_host: str
    databricks_token: str
    volume_path: str
    target_dir: str = "coingecko"
    coins_file: Path = DEFAULT_COINS_FILE

    @classmethod
    def from_env(cls) -> "Settings":
        # Load a local .env file when present. Existing shell/hosting variables
        # take precedence because python-dotenv defaults to override=False.
        load_dotenv()
        required = ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_VOLUME_PATH")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        volume_path = os.environ["DATABRICKS_VOLUME_PATH"].rstrip("/")
        parts = PurePosixPath(volume_path).parts
        if len(parts) < 5 or parts[:2] != ("/", "Volumes"):
            raise ValueError(
                "DATABRICKS_VOLUME_PATH must look like "
                "'/Volumes/<catalog>/<schema>/<volume>'"
            )

        target_dir = os.getenv("DATABRICKS_TARGET_DIR", "coingecko").strip("/")
        if ".." in PurePosixPath(target_dir).parts:
            raise ValueError("DATABRICKS_TARGET_DIR cannot contain '..'")

        return cls(
            databricks_host=os.environ["DATABRICKS_HOST"].rstrip("/"),
            databricks_token=os.environ["DATABRICKS_TOKEN"],
            volume_path=volume_path,
            target_dir=target_dir,
            coins_file=Path(os.getenv("COINGECKO_COINS_FILE", str(DEFAULT_COINS_FILE))),
        )


def load_coin_ids(path: Path) -> list[str]:
    """Read unique CoinGecko IDs, preserving their order."""
    if not path.is_file():
        raise ValueError(f"Coin ID file not found: {path}")

    coin_ids: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        coin_id = raw_line.split("#", 1)[0].strip()
        if not coin_id:
            continue
        if not COIN_ID_PATTERN.fullmatch(coin_id):
            raise ValueError(f"Invalid CoinGecko ID on line {line_number}: {coin_id!r}")
        if coin_id not in seen:
            coin_ids.append(coin_id)
            seen.add(coin_id)

    if not coin_ids:
        raise ValueError(f"No CoinGecko IDs found in {path}")
    return coin_ids


def _session() -> requests.Session:
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "PUT")),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "coingecko-databricks-demo/1.0"
    return session


def _files_api_url(host: str, path: str, *, directory: bool = False) -> str:
    resource = "directories" if directory else "files"
    return f"{host}/api/2.0/fs/{resource}{quote(path, safe='/')}"


def run_ingestion(
    settings: Settings | None = None,
    session: requests.Session | None = None,
) -> list[str]:
    """Run one ingestion and return the Databricks paths that were written.

    Responses remain in memory and are uploaded in a metadata envelope. No local
    temporary files are created.
    """
    settings = settings or Settings.from_env()
    session = session or _session()
    headers = {"Authorization": f"Bearer {settings.databricks_token}"}
    root_destination = f"{settings.volume_path}/{settings.target_dir}".rstrip("/")
    coin_ids = load_coin_ids(settings.coins_file)
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    uploaded: list[str] = []
    for coin_id in coin_ids:
        destination_dir = f"{root_destination}/{coin_id}"
        create_response = session.put(
            _files_api_url(settings.databricks_host, destination_dir + "/", directory=True),
            headers=headers,
            timeout=(10, 60),
        )
        create_response.raise_for_status()

        for name, endpoint_template in ENDPOINTS.items():
            endpoint = endpoint_template.format(coin_id=coin_id)
            source_response = session.get(
                COINGECKO_BASE_URL + endpoint,
                params=REQUEST_PARAMETERS,
                timeout=(10, 30),
            )
            source_response.raise_for_status()
            document = {
                "endpoint": endpoint,
                "parameters": dict(REQUEST_PARAMETERS),
                "response": source_response.json(),
            }
            document_bytes = json.dumps(
                document,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")

            destination = f"{destination_dir}/{name}_{run_timestamp}.json"
            upload_response = session.put(
                _files_api_url(settings.databricks_host, destination),
                params={"overwrite": "false"},
                headers={**headers, "Content-Type": "application/octet-stream"},
                data=document_bytes,
                timeout=(10, 60),
            )
            upload_response.raise_for_status()
            uploaded.append(destination)

    return uploaded
