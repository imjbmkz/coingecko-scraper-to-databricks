"""Optional Vercel Function entry point (scheduling requires a suitable trigger)."""

import json
import os
from http.server import BaseHTTPRequestHandler

from coingecko_ingest import run_ingestion


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        secret = os.getenv("CRON_SECRET")
        authorization = self.headers.get("Authorization")
        if secret and authorization != f"Bearer {secret}":
            self._send_json(401, {"error": "Unauthorized"})
            return

        try:
            uploaded = run_ingestion()
            self._send_json(200, {"uploaded": uploaded})
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

