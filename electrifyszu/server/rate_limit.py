"""Per-IP sliding-window rate limiter.

Defence-in-depth complement to Nginx limit_req.  Protects the Python
process when the port is accessed directly (bypassing Nginx).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler

logger = logging.getLogger("rate-limit")

# ── Rate-limit rules ────────────────────────────────────────────────────────
# (path_key, max_requests_per_window, window_seconds)

_RULES: list[tuple[str, int, float]] = [
    ("/api/status",        10, 60),   # 电费查询：每分钟 10 次
    ("/api/subscriptions",  5, 60),   # 订阅创建：每分钟 5 次
    ("POST",               30, 60),   # 所有 POST 聚合
    ("default",            60, 60),   # 其他 GET 请求
]

# ── Cleanup interval ─────────────────────────────────────────────────────────

_CLEANUP_INTERVAL = 60  # seconds


def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    """Extract the real client IP, preferring the X-Real-IP header set by Nginx."""
    x_real_ip = handler.headers.get("X-Real-IP", "").strip()
    if x_real_ip:
        return x_real_ip
    return handler.client_address[0]


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Each key is ``"<client_ip>:<path_key>"``; each value is a deque of
    request timestamps within the current window.
    """

    def __init__(self, cleanup_interval: float = _CLEANUP_INTERVAL):
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = cleanup_interval

    # ── Public API ────────────────────────────────────────────────────────

    def check(self, handler: BaseHTTPRequestHandler) -> bool:
        """Return True if the request is allowed, False if rate-limited.

        Writes a 429 JSON response + Retry-After header on rejection.
        """
        self._maybe_cleanup()
        ip = _client_ip(handler)
        path = handler.path
        method = handler.command

        max_req, window_sec = self._match_rule(path, method)
        key = f"{ip}:{self._rule_key(path, method)}"
        now = time.monotonic()

        with self._lock:
            timestamps = self._windows[key]
            # Purge timestamps outside the window
            cutoff = now - window_sec
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            if len(timestamps) >= max_req:
                retry_after = int(window_sec)
                logger.warning(
                    "rate-limited %s %s (%d req / %ds window)",
                    ip, path, max_req, int(window_sec),
                )
                self._send_429(handler, retry_after)
                return False

            timestamps.append(now)
            return True

    # ── Internal ───────────────────────────────────────────────────────────

    def _match_rule(self, path: str, method: str) -> tuple[int, float]:
        for path_key, max_req, window_sec in _RULES:
            if path_key == "POST" and method == "POST":
                return max_req, window_sec
            if path_key == "default":
                continue
            if path.startswith(path_key):
                return max_req, window_sec
        # Fallback: default rule
        for path_key, max_req, window_sec in _RULES:
            if path_key == "default":
                return max_req, window_sec
        return 60, 60  # belt and suspenders

    @staticmethod
    def _rule_key(path: str, method: str) -> str:
        if method == "POST":
            return "POST"
        return path

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        with self._lock:
            if now - self._last_cleanup < self._cleanup_interval:
                return  # double-check under lock
            expired = 0
            stale_keys = []
            cutoff = now - (self._cleanup_interval * 2)
            for key, timestamps in self._windows.items():
                while timestamps and timestamps[0] < cutoff:
                    timestamps.popleft()
                    expired += 1
                if not timestamps:
                    stale_keys.append(key)
            for key in stale_keys:
                del self._windows[key]
            self._last_cleanup = now
            if expired:
                logger.debug("cleaned %d expired rate-limit entries", expired)

    @staticmethod
    def _send_429(handler: BaseHTTPRequestHandler, retry_after: int) -> None:
        import json

        payload = json.dumps(
            {"ok": False, "error": "请求过于频繁，请稍后重试", "error_code": "RATE_LIMITED"},
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response(429)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.send_header("Retry-After", str(retry_after))
        handler.end_headers()
        handler.wfile.write(payload)


# Module-level singleton — shared across all requests within a process.
_limiter = RateLimiter()


def check_rate_limit(handler: BaseHTTPRequestHandler) -> bool:
    """Convenience wrapper; returns True when the request is allowed."""
    return _limiter.check(handler)
