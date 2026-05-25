"""Server middleware — request validation and logging."""

from __future__ import annotations

import hmac
import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode, urlparse

from electrifyszu.config import load_dotenv
from electrifyszu.server.handlers.types import ENV_FILE, SENSITIVE_QUERY_KEYS

LIKE_ID_PATTERN = re.compile(r"^svr-[0-9a-f]{16}$")


def validate_same_origin(handler: BaseHTTPRequestHandler) -> bool:
    """Reject cross-site POST requests (XSRF protection)."""
    host = handler.headers.get("Host", "").strip().lower()
    if not host:
        return False
    allowed_origins = {f"http://{host}", f"https://{host}"}
    origin = handler.headers.get("Origin", "").strip().lower()
    if origin:
        return origin in allowed_origins
    referer = handler.headers.get("Referer", "").strip()
    if referer:
        parsed = urlparse(referer)
        referer_origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        return referer_origin in allowed_origins
    return True


def validate_admin_token(handler: BaseHTTPRequestHandler) -> bool:
    load_dotenv(str(ENV_FILE))
    expected = os.getenv("ALERT_ADMIN_TOKEN", "").strip()
    supplied = handler.headers.get("X-Admin-Token", "").strip()
    return bool(expected and supplied and hmac.compare_digest(supplied, expected))


def redact_access_log(message: str) -> str:
    """Redact sensitive query parameters from access log entries."""
    parts = message.split('"')
    for index in range(1, len(parts), 2):
        request_line = parts[index].split()
        if len(request_line) < 2:
            continue
        request_line[1] = _redact_path_query(request_line[1])
        parts[index] = " ".join(request_line)
    return '"'.join(parts)


def _redact_path_query(target: str) -> str:
    parsed = urlparse(target)
    if not parsed.query:
        return target
    query = parse_qs(parsed.query, keep_blank_values=True)
    redacted = {
        key: ["***" if key in SENSITIVE_QUERY_KEYS else value for value in values]
        for key, values in query.items()
    }
    return parsed._replace(query=urlencode(redacted, doseq=True)).geturl()
