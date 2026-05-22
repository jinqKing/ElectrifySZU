from __future__ import annotations

import http.client
import json
import logging
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

import server


class LocalTestServer(ThreadingHTTPServer):
    allow_reuse_address = True


@pytest.fixture
def http_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    likes_file = tmp_path / "likes.json"
    monkeypatch.setattr(server, "LIKES_FILE", likes_file)
    monkeypatch.setenv("ALERT_ADMIN_TOKEN", "secret-token")

    httpd = LocalTestServer(("127.0.0.1", 0), server.DashboardHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def request_json(
    httpd: ThreadingHTTPServer,
    method: str,
    path: str,
    *,
    body: object | str | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    host, port = httpd.server_address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    payload: str | bytes | None
    if body is None:
        payload = None
    elif isinstance(body, (str, bytes)):
        payload = body
    else:
        payload = json.dumps(body)
    conn.request(method, path, body=payload, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    try:
        payload = json.loads(data.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}
    return response.status, payload


def test_post_rejects_cross_site_origin(http_server: ThreadingHTTPServer) -> None:
    status, payload = request_json(
        http_server,
        "POST",
        "/api/like/init",
        body={},
        headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
    )

    assert status == 403
    assert payload["error_code"] == "FORBIDDEN_ORIGIN"


def test_alert_check_requires_post_and_admin_token(
    http_server: ThreadingHTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []

    class FakeRunner:
        def __init__(self, root: Path):
            self.root = root

        def run_once(self, skip_recent: bool = True) -> dict[str, int]:
            calls.append(skip_recent)
            return {"checked": 1}

    monkeypatch.setattr(server, "AlertRunner", FakeRunner)

    status, payload = request_json(http_server, "GET", "/api/alerts/check")
    assert status == 404
    assert calls == []

    status, payload = request_json(
        http_server,
        "POST",
        "/api/alerts/check",
        body={},
        headers={"Content-Type": "application/json"},
    )
    assert status == 401
    assert payload["error_code"] == "UNAUTHORIZED"
    assert calls == []

    status, payload = request_json(
        http_server,
        "POST",
        "/api/alerts/check",
        body={"skipRecent": False},
        headers={"Content-Type": "application/json", "X-Admin-Token": "secret-token"},
    )
    assert status == 200
    assert payload["data"] == {"checked": 1}
    assert calls == [False]


def test_request_body_validation(http_server: ThreadingHTTPServer) -> None:
    status, payload = request_json(
        http_server,
        "POST",
        "/api/like",
        body="[1, 2]",
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert payload["error_code"] == "INVALID_JSON"

    status, payload = request_json(
        http_server,
        "POST",
        "/api/like",
        body="plain",
        headers={"Content-Type": "text/plain"},
    )
    assert status == 415
    assert payload["error_code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_like_requires_issued_hex_id(http_server: ThreadingHTTPServer) -> None:
    status, payload = request_json(
        http_server,
        "POST",
        "/api/like",
        body={"id": "svr-not-hex"},
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert payload["error_code"] == "INVALID_LIKE_ID"

    status, payload = request_json(
        http_server,
        "POST",
        "/api/like",
        body={"id": "svr-0123456789abcdef"},
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert payload["error_code"] == "UNKNOWN_LIKE_ID"

    status, payload = request_json(
        http_server,
        "POST",
        "/api/like/init",
        body={},
        headers={"Content-Type": "application/json"},
    )
    assert status == 200
    like_id = str(payload["id"])

    status, payload = request_json(
        http_server,
        "POST",
        "/api/like",
        body={"id": like_id},
        headers={"Content-Type": "application/json"},
    )
    assert status == 200
    assert payload["already_liked"] is False
    assert payload["count"] == 1


def test_access_log_redacts_sensitive_query_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="server")

    assert (
        server._redact_access_log(
            '"GET /api/subscriptions/verify?token=secret&email=a@example.com HTTP/1.1" 302 -'
        )
        == '"GET /api/subscriptions/verify?token=%2A%2A%2A&email=%2A%2A%2A HTTP/1.1" 302 -'
    )
    assert "secret" not in caplog.text


def test_like_save_is_atomic_and_keeps_fixed_tmp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    likes_path = tmp_path / "likes.json"
    fixed_tmp = likes_path.with_suffix(".tmp")
    fixed_tmp.write_text("sentinel", encoding="utf-8")
    monkeypatch.setattr(server, "LIKES_FILE", likes_path)

    server._save_likes(
        {
            "count": 1,
            "likedIds": ["svr-0123456789abcdef"],
            "seenIds": ["svr-0123456789abcdef"],
            "totalIssued": 1,
        }
    )

    assert json.loads(likes_path.read_text(encoding="utf-8"))["count"] == 1
    assert fixed_tmp.read_text(encoding="utf-8") == "sentinel"


def test_base_url_prefers_public_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://power.example.com/")
    assert server._valid_public_base_url("https://power.example.com/")
