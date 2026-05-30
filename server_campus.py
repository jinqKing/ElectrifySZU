"""ElectrifySZU — Campus proxy server.

Designed to run on the campus-internal machine (behind SZU firewall).
Handles only endpoints that require campus network access.

This server should be reached through an SSH tunnel from the public server.
No public-facing port exposure needed.

Run:
    python server_campus.py --port 8000
"""

from __future__ import annotations

import argparse
import importlib
import logging
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from electrifyszu.logging import setup_logging
from electrifyszu.server.rate_limit import check_rate_limit
from electrifyszu.version import __version__

logger = logging.getLogger("server")

# ── Campus-dependent routes (need SZU internal network) ────────────────────
# These require access to:
#   - DORM_API_BASE  (dorm power system)
#   - APARTMENT_POWER_BASE  (apartment power system)
#   - Building discovery / room ID resolution
CAMPUS_ROUTES: dict[tuple[str, str], tuple[str, str]] = {
    ("GET", "/api/status"):            ("status", "handle_status"),
    ("GET", "/api/buildings"):         ("buildings", "handle_buildings"),
    ("GET", "/api/building-ranking"):  ("buildings", "handle_building_ranking"),
    ("GET", "/api/apartment/floors"):  ("buildings", "handle_apartment_floors"),
    ("GET", "/api/apartment/rooms"):   ("buildings", "handle_apartment_rooms"),
}


def _import_handler(module_name: str, func_name: str):
    mod = importlib.import_module(f"electrifyszu.server.handlers.{module_name}")
    return getattr(mod, func_name)


class CampusAPIHandler(BaseHTTPRequestHandler):
    """Route-based HTTP handler — campus-dependent endpoints only."""

    server_version = f"ElectrifySZU-Campus/{__version__}"

    def do_GET(self) -> None:
        self._request_start = time.time()
        if not check_rate_limit(self):
            return
        parsed = urlparse(self.path)
        key = ("GET", parsed.path)

        if key in CAMPUS_ROUTES:
            module_name, func_name = CAMPUS_ROUTES[key]
            handler_func = _import_handler(module_name, func_name)
            if parsed.query:
                handler_func(self, parse_qs(parsed.query))
            else:
                handler_func(self)
        else:
            self._send_json(
                {"ok": False, "error": "Not found here", "error_code": "NOT_FOUND"},
                status=404,
            )

    def log_message(self, fmt: str, *args: object) -> None:
        elapsed = ""
        if hasattr(self, "_request_start"):
            ms = (time.time() - self._request_start) * 1000
            elapsed = f" ({ms:.0f}ms)"
        message = fmt % args if args else fmt
        logger.info(
            "%s - %s%s",
            self.address_string(),
            message,
            elapsed,
        )

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        import json
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Run the ElectrifySZU campus proxy server."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), CampusAPIHandler)
    logger.info(
        "ElectrifySZU campus proxy: http://%s:%d",
        args.host,
        args.port,
    )
    logger.info(
        "Routes: %d campus-dependent endpoints (accessible via SSH tunnel)",
        len(CAMPUS_ROUTES),
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.warning("Shutdown requested (Ctrl+C)...")
    finally:
        logger.info("Shutting down...")
        server.server_close()
        logger.info("Server stopped.")


if __name__ == "__main__":
    main()
