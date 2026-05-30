"""测试 HTTP_PROXY 白名单校验。"""

from __future__ import annotations

import pytest

from electrifyszu.dorm.proxy import is_safe_proxy_url, get_safe_proxy


class TestIsSafeProxyUrl:
    """测试 is_safe_proxy_url 校验逻辑。"""

    def test_allows_empty_string(self) -> None:
        assert is_safe_proxy_url("") is True

    def test_allows_localhost(self) -> None:
        assert is_safe_proxy_url("http://127.0.0.1:8080") is True
        assert is_safe_proxy_url("http://localhost:3128") is True
        assert is_safe_proxy_url("http://[::1]:8080") is True

    def test_allows_private_192(self) -> None:
        assert is_safe_proxy_url("http://192.168.1.100:3128") is True
        assert is_safe_proxy_url("http://192.168.84.3:9090") is True

    def test_allows_private_10(self) -> None:
        assert is_safe_proxy_url("http://10.0.0.1:8080") is True
        assert is_safe_proxy_url("http://10.99.0.1:3128") is True

    def test_allows_private_172(self) -> None:
        assert is_safe_proxy_url("http://172.16.0.1:8080") is True
        assert is_safe_proxy_url("http://172.31.255.254:3128") is True

    def test_rejects_public_host(self) -> None:
        assert is_safe_proxy_url("http://evil.example.com:8080") is False
        assert is_safe_proxy_url("http://1.2.3.4:3128") is False

    def test_rejects_bare_public_ip(self) -> None:
        assert is_safe_proxy_url("8.8.8.8:8080") is False


class TestGetSafeProxy:
    """测试 get_safe_proxy 端到端行为。"""

    def test_empty_when_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("http_proxy", raising=False)
        assert get_safe_proxy() == ""

    def test_empty_when_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTP_PROXY", "http://evil.example.com:8080")
        result = get_safe_proxy()
        assert result == ""  # 回退直连

    def test_returns_proxy_when_safe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:3128")
        result = get_safe_proxy()
        assert result == "http://127.0.0.1:3128"

    def test_logs_warning_on_reject(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("HTTP_PROXY", "http://evil.example.com:8080")
        import logging
        caplog.set_level(logging.WARNING, logger="dorm.proxy")
        get_safe_proxy()
        assert "rejected" in caplog.text.lower()

    def test_custom_allowlist_env(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("HTTP_PROXY", "http://proxy.internal.com:8080")
        monkeypatch.setenv("ALLOWED_PROXY_HOSTS", "proxy.internal.com")
        assert is_safe_proxy_url("http://proxy.internal.com:8080") is True

    def test_http_proxy_lowercase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:3128")
        result = get_safe_proxy()
        assert result == "http://127.0.0.1:3128"
