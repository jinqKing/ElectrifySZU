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
    base_url: str = ""               # 必须通过 DORM_API_BASE 环境变量配置
    client: str = ""                 # 必须通过 DORM_CLIENT 环境变量配置
    campus_name: str = ""
    building_id: str = ""
    building_name: str = ""
    room_id: str = ""
    room_name: str = ""
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


# ── Apartment config (丽湖校区公寓系统) ──────────────────────────────────────

@dataclass
class ApartmentConfig:
    base_url: str = ""               # 必须通过 APARTMENT_POWER_BASE 环境变量配置
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


# ── Campus group identifiers ─────────────────────────────────────────────────
# Maps logical campus groups to their network client IPs.
# Used by handlers and frontend to identify campus without hardcoding IPs.
#
# Production: configure via CAMPUS_GROUP_<KEY> env vars (e.g. CAMPUS_GROUP_LIHU).
# Development: the hardcoded defaults below suffice.

_CAMPUS_GROUP_DEFAULTS = {
    "lihu":           "172.21.101.11",   # 西丽校区（丽湖）
    "yuehai_north":   "192.168.84.1",    # 粤海/北校区
    "yuehai_south":   "192.168.84.110",  # 粤海/南校区
    "yuehai_newzhai": "192.168.84.87",   # 粤海/新斋区
}


def _load_campus_group() -> dict[str, str]:
    """Load campus-group → IP mapping from CAMPUS_GROUP_<KEY> env vars.

    Returns an empty dict when no such env vars are set, so callers
    can fall back to ``_CAMPUS_GROUP_DEFAULTS``.
    """
    prefix = "CAMPUS_GROUP_"
    result: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith(prefix) and value.strip():
            group_name = key[len(prefix):].lower()
            result[group_name] = value.strip()
    return result


# Populated at import time: defaults as base, env vars override per-key.
CAMPUS_GROUP: dict[str, str] = dict(_CAMPUS_GROUP_DEFAULTS) | _load_campus_group()


def group_for_client(client_ip: str) -> str:
    """Translate a client IP back to its campus group name.

    Returns an empty string when the IP is not recognised.
    """
    for group_name, ip in CAMPUS_GROUP.items():
        if ip == client_ip:
            return group_name
    return ""


def client_for_group(group_name: str) -> str:
    """Translate a campus group name to its client IP.

    Returns an empty string when the group name is not recognised.
    """
    return CAMPUS_GROUP.get(group_name.strip().lower(), "")

# ── Backward-compatible alias ──────────────────────────────────────────────

Config = DormConfig
