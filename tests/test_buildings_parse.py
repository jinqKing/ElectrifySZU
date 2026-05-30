"""测试 buildings.txt 新旧格式兼容性。"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


def _reload_config_default() -> None:
    """Reload electrifyszu.config to its default state."""
    import electrifyszu.config

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


class TestBuildingsFileParsing:
    """测试 load_buildings_file 对新旧 header 格式的兼容。"""

    def test_parses_new_group_format(self, tmp_path: Path) -> None:
        """新格式 group=<name> 可正确解析，client 字段存储 group 名。"""
        content = (
            "# comment\n"
            "## 北校区 group=yuehai_north count=2\n"
            "buildingId=6363\t乔林11-12层\n"
            "buildingId=6364\t乔木11-12层\n"
        )
        buildings_file = tmp_path / "buildings.txt"
        buildings_file.write_text(content, encoding="utf-8")

        from electrifyszu.server.handlers.buildings import load_buildings_file, BUILDINGS_FILE
        import electrifyszu.server.handlers.buildings as bmod

        # Patch BUILDINGS_FILE to use our temp file
        original = bmod.BUILDINGS_FILE
        bmod.BUILDINGS_FILE = buildings_file
        try:
            data = load_buildings_file()
        finally:
            bmod.BUILDINGS_FILE = original

        assert len(data) == 1
        campus = data[0]
        assert campus["client"] == "yuehai_north"
        assert campus["group"] == "yuehai_north"
        assert campus["name"] == "北校区"
        assert len(campus["buildings"]) == 2
        assert campus["buildings"][0]["id"] == "6363"

    def test_parses_old_client_format(self, tmp_path: Path) -> None:
        """旧格式 client=<ip> 仍然可正确解析，client 字段被翻译为 group 名。"""
        content = (
            "## 南校区 client=192.168.84.110 count=1\n"
            "buildingId=6875\t春笛3-8楼\n"
        )
        buildings_file = tmp_path / "buildings_old.txt"
        buildings_file.write_text(content, encoding="utf-8")

        import electrifyszu.server.handlers.buildings as bmod

        original = bmod.BUILDINGS_FILE
        bmod.BUILDINGS_FILE = buildings_file
        try:
            data = bmod.load_buildings_file()
        finally:
            bmod.BUILDINGS_FILE = original

        assert len(data) == 1
        campus = data[0]
        # 旧 IP 应被翻译为 group 名
        assert campus["client"] == "yuehai_south"
        assert campus["group"] == "yuehai_south"
        assert campus["name"] == "南校区"

    def test_group_field_is_populated(self, tmp_path: Path) -> None:
        """解析后的 campus dict 中 group 字段非空。"""
        content = (
            "## 新斋区 group=yuehai_newzhai count=1\n"
            "buildingId=7126\t风槐斋\n"
        )
        buildings_file = tmp_path / "buildings_group.txt"
        buildings_file.write_text(content, encoding="utf-8")

        import electrifyszu.server.handlers.buildings as bmod

        original = bmod.BUILDINGS_FILE
        bmod.BUILDINGS_FILE = buildings_file
        try:
            data = bmod.load_buildings_file()
        finally:
            bmod.BUILDINGS_FILE = original

        assert len(data) == 1
        assert data[0]["group"] not in ("", None)
        assert isinstance(data[0]["group"], str)

    def test_unknown_client_kept_as_is(self, tmp_path: Path) -> None:
        """无法识别的 client/group 值保持原样。"""
        content = (
            "## 未知校区 client=10.0.0.99 count=1\n"
            "buildingId=1\t未知楼栋\n"
        )
        buildings_file = tmp_path / "buildings_unknown.txt"
        buildings_file.write_text(content, encoding="utf-8")

        import electrifyszu.server.handlers.buildings as bmod

        original = bmod.BUILDINGS_FILE
        bmod.BUILDINGS_FILE = buildings_file
        try:
            data = bmod.load_buildings_file()
        finally:
            bmod.BUILDINGS_FILE = original

        assert len(data) == 1
        # 未知 IP → group_for_client 返回 "" → fallback 到原始值
        assert data[0]["client"] == "10.0.0.99"


class TestMergeCampuses:
    """测试 merge_campuses 兼容 group 名作为 client key。"""

    def test_merges_by_group_name(self) -> None:
        from electrifyszu.server.handlers.buildings import merge_campuses

        group_a = [{
            "client": "yuehai_north",
            "name": "北校区",
            "group": "yuehai_north",
            "buildings": [{"id": "6363", "name": "乔林11-12层"}],
        }]
        group_b = [{
            "client": "yuehai_north",
            "name": "北校区",
            "group": "yuehai_north",
            "buildings": [{"id": "6364", "name": "乔木11-12层"}],
        }]
        merged = merge_campuses(group_a, group_b)
        assert len(merged) == 1
        assert len(merged[0]["buildings"]) == 2

    def test_different_groups_kept_separate(self) -> None:
        from electrifyszu.server.handlers.buildings import merge_campuses

        group_a = [{
            "client": "yuehai_north",
            "name": "北校区",
            "group": "yuehai_north",
            "buildings": [{"id": "6363", "name": "乔林"}],
        }]
        group_b = [{
            "client": "yuehai_south",
            "name": "南校区",
            "group": "yuehai_south",
            "buildings": [{"id": "6875", "name": "春笛"}],
        }]
        merged = merge_campuses(group_a, group_b)
        assert len(merged) == 2
