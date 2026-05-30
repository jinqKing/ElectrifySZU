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
    monkeypatch.setenv("ALERT_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("ELECTRIFYSZU_DB_PATH", str(tmp_path / "electrifyszu.db"))

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

    monkeypatch.setattr("electrifyszu.subscription.alerts.AlertRunner", FakeRunner)

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


def test_like_persists_to_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Like-init writes a row, like updates it, and data survives re-read."""
    from electrifyszu.database import get_connection, init_db, set_db_path

    db_path = tmp_path / "electrifyszu.db"
    monkeypatch.setenv("ELECTRIFYSZU_DB_PATH", str(db_path))
    set_db_path(None)  # force re-init with new path
    init_db()

    conn = get_connection()

    # Init a new user
    new_id = f"svr-0123456789abcdef"
    conn.execute("INSERT INTO likes (user_id, liked) VALUES (?, 0)", (new_id,))
    conn.commit()
    assert new_id.startswith("svr-")

    row = conn.execute("SELECT 1 FROM likes WHERE user_id=?", (new_id,)).fetchone()
    assert row is not None  # is_seen

    row = conn.execute("SELECT liked FROM likes WHERE user_id=?", (new_id,)).fetchone()
    assert row is not None and row["liked"] == 0  # not liked yet

    # Like
    conn.execute("UPDATE likes SET liked=1 WHERE user_id=?", (new_id,))
    conn.commit()
    row = conn.execute("SELECT liked FROM likes WHERE user_id=?", (new_id,)).fetchone()
    assert row is not None and row["liked"] == 1

    # Verify stats
    lc = conn.execute("SELECT COUNT(*) FROM likes WHERE liked=1").fetchone()[0]
    uc = conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
    assert lc == 1
    assert uc == 1

    # Verify data persists (re-open connection)
    set_db_path(None)
    conn2 = get_connection()
    lc2 = conn2.execute("SELECT COUNT(*) FROM likes WHERE liked=1").fetchone()[0]
    uc2 = conn2.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
    assert lc2 == 1
    assert uc2 == 1


def test_base_url_prefers_public_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://power.example.com/")
    assert server._valid_public_base_url("https://power.example.com/")


# ── IP 泄露防护测试 ──────────────────────────────────────────────────────────

_IP_PATTERN = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"


def test_demo_status_uses_group_not_ip() -> None:
    """演示数据中 client 字段不应返回内网 IP。"""
    import re
    from electrifyszu.server.handlers.demo import demo_status

    data = demo_status()["data"]
    client_value = str(data.get("client", ""))
    assert not re.match(_IP_PATTERN, client_value), (
        f"demo_status client field leaked IP: {client_value}"
    )


def test_buildings_fallback_json_uses_group_not_ip() -> None:
    """buildings-fallback.json 中 client 字段不应含 IP。"""
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    fb = root / "web" / "data" / "buildings-fallback.json"
    data = json.loads(fb.read_text(encoding="utf-8"))
    for campus in data:
        client = str(campus.get("client", ""))
        assert not re.match(_IP_PATTERN, client), (
            f"buildings-fallback.json leaked IP: {client}"
        )


def test_demo_status_json_uses_group_not_ip() -> None:
    """demo-status.json 中 client 字段不应含 IP。"""
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    fp = root / "web" / "data" / "demo-status.json"
    data = json.loads(fp.read_text(encoding="utf-8"))
    for scenario in data:
        client = str(scenario.get("client", ""))
        assert not re.match(_IP_PATTERN, client), (
            f"demo-status.json leaked IP: {client}"
        )
