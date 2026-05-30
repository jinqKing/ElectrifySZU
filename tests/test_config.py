"""测试 config.py 中的 campus group 翻译函数和环境变量加载。"""

from __future__ import annotations

import importlib
import os

import pytest


def _reload_config_default() -> None:
    """Reload electrifyszu.config to its default state (no CAMPUS_GROUP_* env vars)."""
    import electrifyszu.config

    # Remove any CAMPUS_GROUP_ env vars set by previous tests
    saved: dict[str, str] = {}
    for key in list(os.environ):
        if key.startswith("CAMPUS_GROUP_"):
            saved[key] = os.environ.pop(key)
    try:
        importlib.reload(electrifyszu.config)
    finally:
        os.environ.update(saved)


@pytest.fixture(autouse=True)
def _reset_config_module() -> None:
    """Ensure the config module is in its default state before each test."""
    _reload_config_default()


class TestLoadCampusGroup:
    """测试 CAMPUS_GROUP 从环境变量加载。"""

    def test_loads_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CAMPUS_GROUP_LIHU", "10.0.0.1")
        monkeypatch.setenv("CAMPUS_GROUP_YUEHAI_NORTH", "10.0.0.2")
        from electrifyszu.config import _load_campus_group

        result = _load_campus_group()
        assert result["lihu"] == "10.0.0.1"
        assert result["yuehai_north"] == "10.0.0.2"

    def test_empty_env_returns_empty_dict(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        for key in list(os.environ):
            if key.startswith("CAMPUS_GROUP_"):
                monkeypatch.delenv(key)
        from electrifyszu.config import _load_campus_group

        result = _load_campus_group()
        assert result == {}

    def test_falls_back_to_defaults_when_env_empty(self) -> None:
        """When no CAMPUS_GROUP_* env vars are set, the module-level
        CAMPUS_GROUP dict should contain at least 4 default entries."""
        from electrifyszu.config import CAMPUS_GROUP

        assert len(CAMPUS_GROUP) >= 4
        assert "lihu" in CAMPUS_GROUP
        assert "yuehai_north" in CAMPUS_GROUP
        assert "yuehai_south" in CAMPUS_GROUP
        assert "yuehai_newzhai" in CAMPUS_GROUP

    def test_env_overrides_defaults(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("CAMPUS_GROUP_LIHU", "10.0.0.99")
        import electrifyszu.config

        importlib.reload(electrifyszu.config)
        from electrifyszu.config import CAMPUS_GROUP

        try:
            assert CAMPUS_GROUP["lihu"] == "10.0.0.99"
            # Other keys should still have their defaults (merged)
            assert CAMPUS_GROUP["yuehai_north"] == "192.168.84.1"
        finally:
            # Restore default module state
            _reload_config_default()


class TestGroupTranslation:
    """测试 group_for_client 和 client_for_group 双向翻译。"""

    def test_group_for_client_known_ip(self) -> None:
        from electrifyszu.config import group_for_client, CAMPUS_GROUP

        ip = CAMPUS_GROUP["lihu"]
        assert group_for_client(ip) == "lihu"

    def test_group_for_client_unknown_ip(self) -> None:
        from electrifyszu.config import group_for_client

        assert group_for_client("10.0.0.99") == ""

    def test_group_for_client_empty_string(self) -> None:
        from electrifyszu.config import group_for_client

        assert group_for_client("") == ""

    def test_client_for_group_known(self) -> None:
        from electrifyszu.config import client_for_group, CAMPUS_GROUP

        assert client_for_group("lihu") == CAMPUS_GROUP["lihu"]

    def test_client_for_group_unknown(self) -> None:
        from electrifyszu.config import client_for_group

        assert client_for_group("nonexistent") == ""

    def test_client_for_group_case_insensitive(self) -> None:
        from electrifyszu.config import client_for_group, CAMPUS_GROUP

        assert client_for_group("  LIHU  ") == CAMPUS_GROUP["lihu"]

    def test_roundtrip(self) -> None:
        """group_for_client(client_for_group(x)) should return x for known groups."""
        from electrifyszu.config import group_for_client, client_for_group

        for group_name in ("lihu", "yuehai_north", "yuehai_south", "yuehai_newzhai"):
            ip = client_for_group(group_name)
            assert ip, f"No IP for {group_name}"
            assert group_for_client(ip) == group_name
