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
    # 无 Origin 也无 Referer：放行。
    # 合法场景包括：
    #   - 同源 <form> POST（旧浏览器不发送 Origin）
    #   - 非浏览器客户端（curl、脚本、CLI 工具）
    #   - 反向代理后的内部调用（SSH 隧道、campus 代理）
    # CSRF 攻击依赖浏览器自动携带 cookie，必然发送 Origin 或 Referer，
    # 因此此处放行不会增加 CSRF 风险。
    import logging
    _logger = logging.getLogger("middleware")
    _logger.debug("same-origin: no Origin/Referer header, allowing (likely direct API call)")
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
