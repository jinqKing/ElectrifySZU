from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = PACKAGE_DIR.parent
DEFAULT_ENV_FILE = PROJECT_DIR / ".env"


@dataclass
class Config:
    base_url: str = "http://172.25.100.105:8010/"
    building_code: str = "01"
    room_name: str = "501"
    timeout: int = 15
    low_power_threshold: float = 20.0

    @classmethod
    def from_env(cls, env_file: str | os.PathLike[str] | None = None) -> "Config":
        _load_dotenv(str(env_file or DEFAULT_ENV_FILE))
        return cls(
            base_url=os.getenv("APARTMENT_POWER_BASE", cls.base_url),
            building_code=os.getenv("APARTMENT_BUILDING_CODE", cls.building_code),
            room_name=os.getenv("APARTMENT_ROOM_NAME", cls.room_name),
            timeout=int(os.getenv("APARTMENT_POWER_TIMEOUT", cls.timeout)),
            low_power_threshold=float(
                os.getenv("APARTMENT_LOW_POWER_THRESHOLD", cls.low_power_threshold)
            ),
        )


def _load_dotenv(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
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
