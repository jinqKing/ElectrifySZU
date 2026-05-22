"""测试 server.py 中的纯函数（无需校园网）。"""

from server import demo_status, load_buildings_file, merge_campuses


class TestDemoStatus:
    def test_returns_ok_and_data(self) -> None:
        result = demo_status()
        assert result["ok"] is True
        assert isinstance(result["data"], dict)

    def test_data_has_required_fields(self) -> None:
        data = demo_status()["data"]
        required = [
            "room_name", "remaining", "status", "total_used_kwh",
            "daily_avg_kwh", "est_days_left", "threshold_kwh",
            "last_record", "records", "trend", "recharges",
        ]
        for field in required:
            assert field in data, f"missing field: {field}"

    def test_remaining_is_float(self) -> None:
        data = demo_status()["data"]
        assert isinstance(data["remaining"], (int, float))

    def test_trend_is_list_with_entries(self) -> None:
        trend = demo_status()["data"]["trend"]
        assert isinstance(trend, list)
        assert len(trend) > 0
        for entry in trend:
            assert "date" in entry
            assert "remaining" in entry
            assert "daily_used_kwh" in entry


class TestMergeCampuses:
    def test_empty_inputs(self) -> None:
        assert merge_campuses() == []

    def test_single_group(self) -> None:
        group = [{"client": "10.0.0.1", "name": "粤海", "buildings": [
            {"id": "7126", "name": "风槐斋"},
        ]}]
        result = merge_campuses(group)
        assert len(result) == 1
        assert result[0]["client"] == "10.0.0.1"

    def test_deduplicate_by_client(self) -> None:
        a = [{"client": "10.0.0.1", "name": "粤海", "buildings": [
            {"id": "7126", "name": "风槐斋"},
        ]}]
        b = [{"client": "10.0.0.1", "name": "粤海", "buildings": [
            {"id": "7127", "name": "雨鹃斋"},
        ]}]
        result = merge_campuses(a, b)
        assert len(result) == 1
        assert len(result[0]["buildings"]) == 2

    def test_different_clients_kept_separate(self) -> None:
        a = [{"client": "10.0.0.1", "name": "粤海", "buildings": [
            {"id": "7126", "name": "风槐斋"},
        ]}]
        b = [{"client": "10.0.0.2", "name": "丽湖", "buildings": [
            {"id": "8001", "name": "紫檀轩"},
        ]}]
        result = merge_campuses(a, b)
        assert len(result) == 2

    def test_duplicate_building_id_skipped(self) -> None:
        a = [{"client": "10.0.0.1", "name": "粤海", "buildings": [
            {"id": "7126", "name": "风槐斋"},
        ]}]
        b = [{"client": "10.0.0.1", "name": "粤海", "buildings": [
            {"id": "7126", "name": "风槐斋"},
        ]}]
        result = merge_campuses(a, b)
        assert len(result[0]["buildings"]) == 1
