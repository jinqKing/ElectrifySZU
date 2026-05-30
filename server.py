"""ElectrifySZU HTTP server — route-based dispatcher.

All handler logic lives in electrifyszu/server/handlers/.
This file only routes requests and manages server lifecycle.
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
from electrifyszu.version import __version__
from electrifyszu.ranking.cache import load_ranking_cache
from electrifyszu.server.router import ROUTES
from electrifyszu.server.middleware import (
    validate_same_origin,
    validate_admin_token,
    redact_access_log,
)
from electrifyszu.server.rate_limit import check_rate_limit
from electrifyszu.server.static import serve_static
from electrifyszu.subscription.alerts import (
    AlertRunner,
    shutdown_alert_worker,
    start_alert_worker,
)

# Backward-compatible re-exports (used by tests)
from electrifyszu.server.handlers.demo import demo_status  # noqa: F401
from electrifyszu.server.handlers.buildings import (
    load_buildings_file,  # noqa: F401
    merge_campuses,       # noqa: F401
)
from electrifyszu.server.middleware import redact_access_log as _redact_access_log  # noqa: F401


def _valid_public_base_url(value: str) -> bool:
    from urllib.parse import urlparse
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

logger = logging.getLogger("server")

# Preload ranking cache & mimetypes database to avoid cold-start overhead
try:
    load_ranking_cache()
except Exception:
    logger.warning("Ranking cache preload failed, will lazy-load on first request")
mimetypes.guess_type("index.html")


class DashboardHandler(BaseHTTPRequestHandler):
    """Route-based HTTP handler — delegates all logic to handler modules."""

    server_version = f"ElectrifySZU/{__version__}"

    def do_GET(self) -> None:
        self._request_start = time.time()
        if not check_rate_limit(self):
            return
        parsed = urlparse(self.path)
        key = ("GET", parsed.path)
        if key in ROUTES:
            try:
                module_name, func_name = ROUTES[key]
                handler_mod = importlib.import_module(
                    f"electrifyszu.server.handlers.{module_name}"
                )
                handler_func = getattr(handler_mod, func_name)
                if parsed.query:
                    from urllib.parse import parse_qs
                    handler_func(self, parse_qs(parsed.query))
                else:
                    handler_func(self)
            except Exception:
                logger.exception("Unhandled error in GET %s", parsed.path)
                try:
                    self._send_json(
                        {"ok": False, "error": "Internal server error", "error_code": "INTERNAL_ERROR"},
                        status=500,
                    )
                except Exception:
                    pass
        else:
            serve_static(self, parsed.path)

    def do_POST(self) -> None:
        self._request_start = time.time()
        if not check_rate_limit(self):
            return
        if not validate_same_origin(self):
            self._send_json(
                {"ok": False, "error": "Forbidden origin", "error_code": "FORBIDDEN_ORIGIN"},
                status=403,
            )
            return

        parsed = urlparse(self.path)
        key = ("POST", parsed.path)
        if key not in ROUTES:
            self._send_json(
                {"ok": False, "error": "Not found", "error_code": "NOT_FOUND"},
                status=404,
            )
            return

        # Special: alert check requires admin token
        if parsed.path == "/api/alerts/check" and not validate_admin_token(self):
            self._send_json(
                {"ok": False, "error": "Invalid admin token", "error_code": "UNAUTHORIZED"},
                status=401,
            )
            return

        try:
            module_name, func_name = ROUTES[key]
            handler_mod = importlib.import_module(
                f"electrifyszu.server.handlers.{module_name}"
            )
            handler_func = getattr(handler_mod, func_name)
            if parsed.query:
                from urllib.parse import parse_qs
                handler_func(self, parse_qs(parsed.query))
            else:
                handler_func(self)
        except Exception:
            logger.exception("Unhandled error in POST %s", parsed.path)
            try:
                self._send_json(
                    {"ok": False, "error": "Internal server error", "error_code": "INTERNAL_ERROR"},
                    status=500,
                )
            except Exception:
                pass

    def log_message(self, fmt: str, *args: object) -> None:
        """Structured access log with timing."""
        elapsed = ""
        if hasattr(self, "_request_start"):
            ms = (time.time() - self._request_start) * 1000
            elapsed = f" ({ms:.0f}ms)"
        message = fmt % args if args else fmt
        logger.info(
            "%s - %s%s",
            self.address_string(),
            redact_access_log(message),
            elapsed,
        )

    # ── Thin JSON helpers (kept here so handlers just call self._send_json) ──

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        import json
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="Run the ElectrifySZU dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--check-now",
        action="store_true",
        help="Run one alert check immediately before serving.",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Do not skip subscriptions already alerted today.",
    )
    args = parser.parse_args()

    ROOT = Path(__file__).resolve().parent
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    logger.info("ElectrifySZU dashboard: http://%s:%d", args.host, args.port)
    if args.check_now:
        stats = AlertRunner(ROOT).run_once(skip_recent=not args.no_skip)
        logger.info("startup check finished: %s", stats)
    alert_thread = start_alert_worker(ROOT, skip_recent=not args.no_skip)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.warning("Shutdown requested (Ctrl+C)...")
    finally:
        logger.info("Shutting down...")
        shutdown_alert_worker()
        logger.info("Closing server socket, draining in-flight requests...")
        server.server_close()
        alert_thread.join(timeout=10)
        if alert_thread.is_alive():
            logger.warning("Alert worker thread did not exit within timeout.")
        logger.info("Server stopped.")


if __name__ == "__main__":
    main()
