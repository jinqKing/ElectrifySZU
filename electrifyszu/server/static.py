"""Static file serving — falls back when no API route matches."""

from __future__ import annotations

import mimetypes
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"


CACHE_MAX_AGE: dict[str, int] = {
    "image": 86400,       # 1 day — png, webp, jpg, ico, svg
    "stylesheet": 3600,   # 1 hour — css
    "script": 3600,       # 1 hour — js
    "document": 0,        # no cache — html
    "other": 0,           # no cache — fallback
}


def _cache_seconds(content_type: str) -> int:
    if content_type.startswith("image/"):
        return CACHE_MAX_AGE["image"]
    if content_type in {"text/css", "text/stylesheet"}:
        return CACHE_MAX_AGE["stylesheet"]
    if content_type in {"application/javascript", "text/javascript", "application/x-javascript"}:
        return CACHE_MAX_AGE["script"]
    if content_type in {"text/html", "application/xhtml+xml"}:
        return CACHE_MAX_AGE["document"]
    return CACHE_MAX_AGE["other"]


def serve_static(handler: BaseHTTPRequestHandler, path: str) -> None:
    if path in {"", "/"}:
        path = "/index.html"
    base_dir = WEB_DIR.resolve()
    target = (base_dir / path.lstrip("/")).resolve()
    try:
        target.relative_to(base_dir)
    except ValueError:
        handler.send_error(404)
        return

    if not target.is_file():
        handler.send_error(404)
        return

    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    data = target.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    max_age = _cache_seconds(content_type)
    if max_age > 0:
        handler.send_header("Cache-Control", f"public, max-age={max_age}")
    handler.end_headers()
    handler.wfile.write(data)
