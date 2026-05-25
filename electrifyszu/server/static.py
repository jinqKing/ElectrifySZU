"""Static file serving — falls back when no API route matches."""

from __future__ import annotations

import mimetypes
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"


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
    handler.end_headers()
    handler.wfile.write(data)
