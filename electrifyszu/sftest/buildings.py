"""Sftest (后勤部新宿舍) building registry.

Nine dormitories served by the sftest.hqb.szu.edu.cn electricity system.
Each building uses a UUID ``guid`` for API calls and a short
``prefix`` for room identifiers (e.g. DFX-101).
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Known buildings ─────────────────────────────────────────────────────────
# (id, name, prefix, guid, floors)
_BUILDINGS: list[tuple[str, str, str, str, list[int]]] = [
    ("01", "海桐斋", "HTZ", "C36E7318-870C-D13F-806D-6CFF785E6DDB", list(range(1, 7))),
    ("02", "米兰斋", "MLZ", "D18222DF-D667-E509-68E2-BC516CBBAB8D", list(range(1, 7))),
    ("03", "山茶斋", "SCZ", "F273E9DE-28CD-98DB-92FB-D7BC560D8610", list(range(1, 9))),
    ("04", "红榴斋", "HLZ", "917E003E-A041-6332-B66C-9C8F54460AB3", list(range(1, 9))),
    ("05", "桃李斋", "TLZ", "B5E4F86E-3690-2011-668A-8D48D9050C9A", list(range(1, 7))),
    ("06", "凌霄斋", "LXZ", "4D6FC32A-C86A-E03C-A3B3-7914C67BC665", list(range(1, 7))),
    ("07", "银桦斋", "YHZ", "16804A62-6F47-E04E-9803-3D875D06D661", list(range(1, 7))),
    ("08", "丹枫轩", "DFX", "27B5D48F-14F9-8576-F6D1-878E7C909BD0", list(range(1, 6))),
    ("09", "木犀轩", "MXX", "B66C5C8C-68A2-2128-BB61-D57DACBB33C8", list(range(1, 5))),
]


@dataclass(frozen=True)
class SftestBuilding:
    code: str        # "01".."09"
    name: str        # 中文名
    prefix: str      # 房间前缀 DFX/HTZ/...
    guid: str        # 楼栋 UUID
    floors: list[int]


def load_buildings() -> dict[str, SftestBuilding]:
    return {
        code: SftestBuilding(code=code, name=name, prefix=prefix, guid=guid, floors=floors)
        for code, name, prefix, guid, floors in _BUILDINGS
    }


def get_building(code: str) -> SftestBuilding:
    buildings = load_buildings()
    if code not in buildings:
        known = ", ".join(f"{b.code}({b.name})" for b in buildings.values())
        raise ValueError(f"未知楼栋编码 {code}；已知楼栋：{known}")
    return buildings[code]


def building_code_for_prefix(room_name: str) -> str | None:
    """Infer building code from room prefix (e.g. 'DFX-101' → '08')."""
    buildings = load_buildings()
    for b in buildings.values():
        if room_name.upper().startswith(b.prefix):
            return b.code
    return None
