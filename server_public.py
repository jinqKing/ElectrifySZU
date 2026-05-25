"""ElectrifySZU — Public API server.

Designed to run on the public-facing server (129.204.227.179).
Handles only endpoints that do NOT need campus network access.

Campus-dependent endpoints (/api/status, /api/buildings, etc.)
are proxied via SSH tunnel to the campus machine.

Run:
    python server_public.py --port 8000

Or in Docker:
    docker run electrifyszu-public
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
from electrifyszu.server.middleware import (
    validate_same_origin,
    validate_admin_token,
    redact_access_log,
)
from electrifyszu.database import ensure_db
from electrifyszu.subscription.alerts import (
    AlertRunner,
    shutdown_alert_worker,
    start_alert_worker,
)

logger = logging.getLogger("server")

# ── Public-safe routes (no campus network dependency) ───────────────────────
# These are the only endpoints this server handles.
# Campus endpoints like /api/status are proxied through Nginx → SSH tunnel.
PUBLIC_ROUTES: dict[tuple[str, str], tuple[str, str]] = {
    # Demo / health / version
    ("GET", "/api/demo-status"):      ("demo", "handle_demo"),
    ("GET", "/api/version"):          ("demo", "handle_version"),
    ("GET", "/api/health"):           ("demo", "handle_health"),
    ("GET", "/api/github-stars"):     ("demo", "handle_github_stars"),

    # Subscriptions (email-based, uses SMTP — no campus network needed)
    ("POST", "/api/subscriptions"):        ("subscription", "handle_subscription_create"),
    ("GET", "/api/subscriptions/verify"):  ("subscription", "handle_subscription_verify"),
    ("GET", "/api/unsubscribe"):           ("subscription", "handle_unsubscribe"),
    ("POST", "/api/alerts/check"):         ("subscription", "handle_alert_check"),

    # Likes / stats (SQLite-backed, lives on public server)
    ("POST", "/api/like/init"):       ("likes", "handle_like_init"),
    ("POST", "/api/like"):            ("likes", "handle_like"),
    ("GET", "/api/like/count"):       ("likes", "handle_like_count"),
    ("GET", "/api/like/my"):          ("likes", "handle_like_my"),
    ("GET", "/api/stats"):            ("likes", "handle_stats"),
}


def _import_handler(module_name: str, func_name: str):
    """Lazy-import a handler module from electrifyszu.server.handlers."""
    mod = importlib.import_module(f"electrifyszu.server.handlers.{module_name}")
    return getattr(mod, func_name)


class PublicAPIHandler(BaseHTTPRequestHandler):
    """Route-based HTTP handler — public-safe endpoints only."""

    server_version = f"ElectrifySZU-Public/{__version__}"

    def do_GET(self) -> None:
        self._request_start = time.time()
        parsed = urlparse(self.path)
        key = ("GET", parsed.path)

        if key in PUBLIC_ROUTES:
            module_name, func_name = PUBLIC_ROUTES[key]
            handler_func = _import_handler(module_name, func_name)
            if parsed.query:
                handler_func(self, parse_qs(parsed.query))
            else:
                handler_func(self)
        else:
            self._send_json(
                {"ok": False, "error": "Not found", "error_code": "NOT_FOUND"},
                status=404,
            )

    def do_POST(self) -> None:
        self._request_start = time.time()
        if not validate_same_origin(self):
            self._send_json(
                {"ok": False, "error": "Forbidden origin", "error_code": "FORBIDDEN_ORIGIN"},
                status=403,
            )
            return

        parsed = urlparse(self.path)
        key = ("POST", parsed.path)

        if key not in PUBLIC_ROUTES:
            self._send_json(
                {"ok": False, "error": "Not found", "error_code": "NOT_FOUND"},
                status=404,
            )
            return

        # Alert check requires admin token
        if parsed.path == "/api/alerts/check" and not validate_admin_token(self):
            self._send_json(
                {"ok": False, "error": "Invalid admin token", "error_code": "UNAUTHORIZED"},
                status=401,
            )
            return

        module_name, func_name = PUBLIC_ROUTES[key]
        handler_func = _import_handler(module_name, func_name)
        if parsed.query:
            handler_func(self, parse_qs(parsed.query))
        else:
            handler_func(self)

    def log_message(self, fmt: str, *args: object) -> None:
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
        description="Run the ElectrifySZU public API server."
    )
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

    # Ensure SQLite database exists
    ensure_db()
    logger.info("SQLite database ready")

    ROOT = Path(__file__).resolve().parent
    server = ThreadingHTTPServer((args.host, args.port), PublicAPIHandler)
    logger.info(
        "ElectrifySZU public API server: http://%s:%d",
        args.host,
        args.port,
    )
    logger.info(
        "Routes: %d public-safe endpoints (campus routes proxied via tunnel)",
        len(PUBLIC_ROUTES),
    )

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
