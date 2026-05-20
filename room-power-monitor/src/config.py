# 宿舍不断电 — 配置管理

import os
from dataclasses import dataclass


@dataclass
class Config:
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
    def from_env(cls, env_file: str = ".env") -> "Config":
        _load_dotenv(env_file)
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


def _load_dotenv(path: str):
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if val and (val.startswith('"') or val.startswith("'")):
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val
