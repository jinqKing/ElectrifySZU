"""Unified configuration for ElectrifySZU.

Provides shared `_load_dotenv` plus separate config dataclasses
for the dormitory campus system and the apartment (丽湖) system.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# ── Shared environment loader ──────────────────────────────────────────────

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_DIR / ".env"


def load_dotenv(path: str | os.PathLike[str] | None = None) -> None:
    """Load .env entries into os.environ (never overwrites existing values)."""
    filepath = path or str(DEFAULT_ENV_FILE)
    if not os.path.isfile(filepath):
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if val and (val.startswith('"') or val.startswith("'")):
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val


# Keep the old name as an alias for backward compatibility
_load_dotenv = load_dotenv


# ── Dorm campus config (粤海 / 北校区 / 南校区 / 新斋区) ────────────────────

@dataclass
class DormConfig:
    base_url: str = "http://192.168.84.3:9090/cgcSims"
    client: str = "192.168.84.87"
    campus_name: str = "深大新斋区"
    building_id: str = "7126"
    building_name: str = "风槐斋"
    room_id: str = "7322"
    room_name: str = "713"
    poll_interval: int = 3600
    low_power_threshold: float = 20.0

    @classmethod
    def from_env(cls, env_file: str | os.PathLike[str] | None = None) -> "DormConfig":
        load_dotenv(str(env_file or DEFAULT_ENV_FILE))
        return cls(
            base_url=os.getenv("DORM_API_BASE", cls.base_url),
            client=os.getenv("DORM_CLIENT", cls.client),
            campus_name=os.getenv("DORM_CAMPUS_NAME", cls.campus_name),
            building_id=os.getenv("DORM_BUILDING_ID", cls.building_id),
            building_name=os.getenv("DORM_BUILDING_NAME", cls.building_name),
            room_id=os.getenv("DORM_ROOM_ID", cls.room_id),
            room_name=os.getenv("DORM_ROOM_NAME", cls.room_name),
            poll_interval=int(os.getenv("DORM_POLL_INTERVAL", cls.poll_interval)),
            low_power_threshold=float(
                os.getenv("DORM_LOW_POWER_THRESHOLD", cls.low_power_threshold)
            ),
        )


# ── Apartment config (丽湖 172.25.100.105:8010) ─────────────────────────────

@dataclass
class ApartmentConfig:
    base_url: str = "http://172.25.100.105:8010/"
    building_code: str = "01"
    room_name: str = "501"
    timeout: int = 15
    low_power_threshold: float = 20.0

    @classmethod
    def from_env(cls, env_file: str | os.PathLike[str] | None = None) -> "ApartmentConfig":
        load_dotenv(str(env_file or DEFAULT_ENV_FILE))
        return cls(
            base_url=os.getenv("APARTMENT_POWER_BASE", cls.base_url),
            building_code=os.getenv("APARTMENT_BUILDING_CODE", cls.building_code),
            room_name=os.getenv("APARTMENT_ROOM_NAME", cls.room_name),
            timeout=int(os.getenv("APARTMENT_POWER_TIMEOUT", cls.timeout)),
            low_power_threshold=float(
                os.getenv("APARTMENT_LOW_POWER_THRESHOLD", cls.low_power_threshold)
            ),
        )


# ── Legacy alias (keep old code working) ───────────────────────────────────

# These aliases let code that does `from src.config import Config, _load_dotenv`
# continue working via the compatibility wrapper in room-power-monitor/src/.
Config = DormConfig
