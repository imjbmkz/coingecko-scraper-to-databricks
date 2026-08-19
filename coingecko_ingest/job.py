"""Fetch raw CoinGecko JSON responses and upload them to a Databricks Volume."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Mapping
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
ENDPOINTS: Mapping[str, str] = {
    "market_chart": "/coins/bitcoin/market_chart?vs_currency=usd&days=1",
    "ohlc": "/coins/bitcoin/ohlc?vs_currency=usd&days=1",
}


@dataclass(frozen=True)
class Settings:
    databricks_host: str
    databricks_token: str
    volume_path: str
    target_dir: str = "coingecko/bitcoin"

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

        target_dir = os.getenv("DATABRICKS_TARGET_DIR", "coingecko/bitcoin").strip("/")
        if ".." in PurePosixPath(target_dir).parts:
            raise ValueError("DATABRICKS_TARGET_DIR cannot contain '..'")

        return cls(
            databricks_host=os.environ["DATABRICKS_HOST"].rstrip("/"),
            databricks_token=os.environ["DATABRICKS_TOKEN"],
            volume_path=volume_path,
            target_dir=target_dir,
        )


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

    Responses remain in memory and are uploaded unchanged as raw bytes. No local
    temporary files are created.
    """
    settings = settings or Settings.from_env()
    session = session or _session()
    headers = {"Authorization": f"Bearer {settings.databricks_token}"}
    destination_dir = f"{settings.volume_path}/{settings.target_dir}".rstrip("/")

    create_response = session.put(
        _files_api_url(settings.databricks_host, destination_dir + "/", directory=True),
        headers=headers,
        timeout=(10, 30),
    )
    create_response.raise_for_status()

    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    uploaded: list[str] = []
    for name, endpoint in ENDPOINTS.items():
        source_response = session.get(COINGECKO_BASE_URL + endpoint, timeout=(10, 30))
        source_response.raise_for_status()
        # Validate that CoinGecko returned JSON, while preserving the original bytes.
        source_response.json()

        destination = f"{destination_dir}/{name}_{run_timestamp}.json"
        upload_response = session.put(
            _files_api_url(settings.databricks_host, destination),
            params={"overwrite": "false"},
            headers={**headers, "Content-Type": "application/octet-stream"},
            data=source_response.content,
            timeout=(10, 60),
        )
        upload_response.raise_for_status()
        uploaded.append(destination)

    return uploaded
