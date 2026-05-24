from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from building_power_ranking.cache import (
    build_random_sample_plan,
    cache_with_rankings,
    cached_ranking_for,
    demo_ranking_from_plan,
    load_ranking_cache,
    save_ranking_cache,
)
from building_power_ranking.floor_probe import (
    FloorRangeRecord,
    candidate_floor_range,
    load_floor_ranges,
    parse_explicit_floor_range,
    save_floor_ranges,
)
from building_power_ranking.ranking import build_ranking, generate_sample_rooms, mask_room_name


class BuildingPowerRankingTests(unittest.TestCase):
    def test_parse_explicit_floor_range(self) -> None:
        self.assertEqual(parse_explicit_floor_range("夏筝3-17楼"), (3, 17))
        self.assertEqual(parse_explicit_floor_range("乔梧阁11-20层"), (11, 20))
        self.assertEqual(parse_explicit_floor_range("乔梧阁1-20"), (1, 20))

    def test_candidate_range_defaults_to_second_through_twentieth_floor(self) -> None:
        self.assertEqual(candidate_floor_range("风槐斋", "深大新斋区"), (2, 20, "public_reference_yuehai"))
        self.assertEqual(candidate_floor_range("未知楼栋", "未知校区"), (2, 20, "default"))

    def test_floor_range_json_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ranges.json"
            data = {"client:1": {"detected_min_floor": 2, "detected_max_floor": 17}}
            save_floor_ranges(data, path)
            self.assertEqual(load_floor_ranges(path), data)

    def test_generate_samples_and_mask_room_name(self) -> None:
        self.assertEqual(generate_sample_rooms(2, 3), ["201", "205", "210", "301", "305", "310"])
        self.assertEqual(mask_room_name("713"), "7**")
        self.assertEqual(mask_room_name("1001"), "1***")

    def test_random_sample_plan_records_floor_and_room_ranges(self) -> None:
        plan = build_random_sample_plan(
            client="client",
            campus_name="campus",
            building_id="7126",
            building_name="building",
            min_floor=2,
            max_floor=3,
            rooms_per_floor=2,
            room_suffix_start=1,
            room_suffix_end=4,
            seed=7,
        )
        self.assertEqual(plan["floor_range"]["min"], 2)
        self.assertEqual(plan["floor_range"]["max"], 3)
        self.assertEqual(plan["room_suffix_range"], {"start": 1, "end": 4})
        self.assertEqual(plan["sample_count"], 4)
        self.assertEqual(sorted(plan["rooms_by_floor"].keys()), ["2", "3"])

    def test_ranking_cache_roundtrip_and_lookup(self) -> None:
        plan = build_random_sample_plan(
            client="client",
            campus_name="campus",
            building_id="7126",
            building_name="building",
            min_floor=2,
            max_floor=2,
            rooms_per_floor=1,
            seed=7,
        )
        ranking = demo_ranking_from_plan(plan, seed=7, generated_at="2026-05-21T00:00:00")
        cache = cache_with_rankings([ranking], source="demo", generated_at="2026-05-21T00:00:00")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ranking_cache.json"
            save_ranking_cache(cache, path)
            loaded = load_ranking_cache(path, fallback_path=None)

        item = cached_ranking_for(loaded, client="client", building_id="7126")
        self.assertIsNotNone(item)
        self.assertEqual(item["source"], "demo")
        self.assertGreater(len(item["ranking"]), 0)

    def test_build_ranking_sorts_and_skips_failed_rooms(self) -> None:
        config = SimpleNamespace(low_power_threshold=20, client="")
        room_ids = {"201": "r201", "205": "r205", "210": "r210"}
        totals = {"201": 3.0, "205": 9.0, "210": 5.0}

        class FakeApi:
            def __init__(self, _config: object) -> None:
                pass

            def get_status(self, room_id: str, room_name: str, days: int, threshold: float) -> dict[str, object]:
                return {
                    "total_used_kwh": totals[room_name],
                    "daily_avg_kwh": totals[room_name] / days,
                    "remaining": 20 - totals[room_name],
                    "last_record": "2026-05-20",
                    "status": "ok",
                }

        def fake_discover(building_id: str, room_name: str, client_ip: str) -> str | None:
            return room_ids.get(room_name)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ranges.json"
            save_floor_ranges(
                {
                    "client:7126": {
                        **FloorRangeRecord(
                            client="client",
                            campus_name="campus",
                            building_id="7126",
                            building_name="building",
                            candidate_min_floor=2,
                            candidate_max_floor=2,
                            detected_min_floor=2,
                            detected_max_floor=2,
                            source="test",
                            sample_valid_rooms=[],
                            failed_candidates=[],
                            probed_at="2026-05-20T00:00:00",
                        ).__dict__,
                    }
                },
                path,
            )
            result = build_ranking(
                config=config,
                client="client",
                campus_name="campus",
                building_id="7126",
                building_name="building",
                days=3,
                api_factory=FakeApi,
                discover_room_id=fake_discover,
                floor_range_path=str(path),
            )

        self.assertEqual([row["room_name_masked"] for row in result["ranking"]], ["2**", "2**", "2**"])
        self.assertEqual([row["total_used_kwh"] for row in result["ranking"]], [9.0, 5.0, 3.0])
        self.assertEqual(result["stats"], {"sample_count": 3, "ranked_count": 3, "skipped_count": 0})


if __name__ == "__main__":
    unittest.main()
