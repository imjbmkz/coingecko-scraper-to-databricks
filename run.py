"""Command-line entry point for the scheduled ingestion job."""

import json

from coingecko_ingest import run_ingestion


if __name__ == "__main__":
    print(json.dumps({"uploaded": run_ingestion()}, indent=2))

