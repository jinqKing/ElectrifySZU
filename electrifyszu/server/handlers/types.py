"""Shared types, constants, and utilities for server handlers.

Defines a Handler protocol so every handler gets:
  - query_value(key) → URL query param
  - read_body()        → parsed POST body
  - send_json(data)    → JSON response
  - error(code, msg)   → error response
  - redirect(url)      → 302 redirect
  - headers            → request headers
  - env(key)           → env var lookup
"""

from __future__ import annotations

import os
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
LIKES_FILE = ROOT / "data" / "likes.json"
MAX_REQUEST_BODY_BYTES = 64 * 1024

SENSITIVE_QUERY_KEYS = {"token", "email", "userId", "id"}


class RequestError(Exception):
    """Raised after an error response has already been sent."""


class Handler(Protocol):
    """Protocol that DashboardHandler satisfies for all handler functions."""

    path: str
    headers: Any  # http.client.HTTPMessage
    client_address: tuple[str, int]

    def send_response(self, code: int) -> None: ...
    def send_header(self, keyword: str, value: str) -> None: ...
    def end_headers(self) -> None: ...
    def send_error(self, code: int, message: str | None = None) -> None: ...

    @property
    def rfile(self) -> Any: ...
    @property
    def wfile(self) -> Any: ...


# ── Utility functions shared across handlers ─────────────────────────────────

def query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    return values[0].strip() if values else ""


def content_type_is(content_type: str, expected: str) -> bool:
    return content_type.split(";", 1)[0].strip().lower() == expected


def truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def read_request_data(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    """Parse POST body as JSON, multipart/form-data, or URL-encoded form."""
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError:
        send_error(handler, "INVALID_CONTENT_LENGTH", "Invalid Content-Length", status=400)
        raise RequestError()
    if length > MAX_REQUEST_BODY_BYTES:
        send_error(handler, "REQUEST_TOO_LARGE", "Request body too large", status=413)
        raise RequestError()
    import json
    body = handler.rfile.read(length)
    content_type = handler.headers.get("Content-Type", "")
    if not content_type:
        return {}
    if content_type_is(content_type, "application/json"):
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            send_error(handler, "INVALID_JSON", "Invalid JSON body", status=400)
            raise RequestError()
        if not isinstance(payload, dict):
            send_error(handler, "INVALID_JSON", "JSON body must be an object", status=400)
            raise RequestError()
        return {str(key): _clean_request_value(value) for key, value in payload.items()}
    if "multipart/form-data" in content_type:
        headers = f"Content-Type: {content_type}\n\n".encode("utf-8")
        message = BytesParser(policy=policy.default).parsebytes(headers + body)
        return {
            str(part.get_param("name", header="content-disposition")): part.get_payload(
                decode=True
            ).decode(part.get_content_charset("utf-8")).strip()
            for part in message.iter_parts()
            if part.get_param("name", header="content-disposition")
        }
    if content_type_is(content_type, "application/x-www-form-urlencoded"):
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError:
            send_error(handler, "INVALID_FORM_BODY", "Invalid form body", status=400)
            raise RequestError()
        parsed = parse_qs(decoded, keep_blank_values=True)
        return {key: values[0].strip() if values else "" for key, values in parsed.items()}
    send_error(handler, "UNSUPPORTED_MEDIA_TYPE", "Unsupported Content-Type", status=415)
    raise RequestError()


# ── Response helpers ─────────────────────────────────────────────────────────

def send_json(handler: BaseHTTPRequestHandler, payload: dict[str, object], status: int = 200) -> None:
    import json
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.end_headers()
    handler.wfile.write(data)


def send_error(
    handler: BaseHTTPRequestHandler,
    code: str,
    message: str,
    hint: str = "",
    status: int = 400,
) -> None:
    send_json(
        handler,
        {"ok": False, "error": message, "hint": hint, "error_code": code},
        status=status,
    )


def redirect_to(handler: BaseHTTPRequestHandler, path: str) -> None:
    from urllib.parse import urlencode
    handler.send_response(302)
    handler.send_header("Location", path)
    handler.send_header("Content-Length", "0")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.end_headers()


# ── Internal ─────────────────────────────────────────────────────────────────

def _clean_request_value(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value
