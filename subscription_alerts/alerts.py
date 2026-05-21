from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
MONITOR_DIR = PROJECT_DIR / "room-power-monitor"
if str(MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(MONITOR_DIR))

from src.api import DormApi
from src.config import Config, _load_dotenv
from src.discover import discover_room_id

from .email_service import EmailConfig, EmailService
from .email_templates import alert_content, alert_subject
from .store import Subscription, SubscriptionStore


@dataclass(frozen=True)
class AlertSettings:
    csv_path: Path
    check_time: str
    loop_interval_seconds: int
    base_url: str
    env_path: Path

    @classmethod
    def from_env(cls, project_dir: Path) -> "AlertSettings":
        env_path = project_dir / ".env"
        _load_dotenv(str(env_path))
        default_csv = project_dir / "data" / "subscriptions.csv"
        csv_path = Path(_env("SUBSCRIPTIONS_CSV", str(default_csv)))
        if not csv_path.is_absolute():
            csv_path = project_dir / csv_path
        return cls(
            csv_path=csv_path,
            check_time=_env("ALERT_CHECK_TIME", "08:00"),
            loop_interval_seconds=max(int(_env("ALERT_LOOP_INTERVAL", "300")), 30),
            base_url=_env("PUBLIC_BASE_URL", ""),
            env_path=env_path,
        )


class AlertRunner:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.settings = AlertSettings.from_env(project_dir)
        self.store = SubscriptionStore(self.settings.csv_path)

    def run_once(self, skip_recent: bool = True) -> dict[str, int]:
        today = date.today().isoformat()
        stats = {"checked": 0, "sent": 0, "skipped": 0, "failed": 0}
        for subscription in self.store.list_enabled():
            stats["checked"] += 1
            try:
                if skip_recent and subscription.last_alert_date == today:
                    stats["skipped"] += 1
                    print(
                        "[alert] skipped "
                        f"{subscription.email} {subscription.building_name} "
                        f"{subscription.room_name} {subscription.last_alert_date}"
                    )
                    continue
                sent = self._check_subscription(subscription, today)
                if sent:
                    stats["sent"] += 1
                    print(
                        "[alert] sent "
                        f"{subscription.email} {subscription.building_name} "
                        f"{subscription.room_name} {subscription.last_alert_date}"
                    )
                else:
                    stats["skipped"] += 1
                    print(
                        "[alert] skipped because of _check_subscription "
                        f"{subscription.email} {subscription.building_name} "
                        f"{subscription.room_name} {subscription.last_alert_date}"
                    )
            except Exception as exc:
                stats["failed"] += 1
                print(
                    "[alert] failed "
                    f"{subscription.email} {subscription.building_name} "
                    f"{subscription.room_name}: {exc}"
                )
        return stats

    def run_forever(self, skip_recent: bool = True) -> None:
        print(
            "[alert] daily subscription worker started; "
            f"check_time={self.settings.check_time}, skip_recent={skip_recent}, csv={self.settings.csv_path}"
        )
        while True:
            now = datetime.now()
            next_run = _next_run_at(now, self.settings.check_time)
            sleep_seconds = max((next_run - now).total_seconds(), 1)
            time.sleep(min(sleep_seconds, self.settings.loop_interval_seconds))
            if datetime.now() >= next_run:
                stats = self.run_once(skip_recent=skip_recent)
                print(f"[alert] daily check finished: {stats}")
                time.sleep(60)

    def _check_subscription(self, subscription: Subscription, today: str) -> bool:
        config = Config.from_env(str(self.settings.env_path))
        config.client = subscription.client
        room_id = discover_room_id(
            building_id=subscription.building_id,
            room_name=subscription.room_name,
            client_ip=subscription.client,
        )
        if not room_id:
            raise LookupError(
                f"未找到 {subscription.campus_name} "
                f"{subscription.building_name} {subscription.room_name} 房间。"
            )

        result = DormApi(config).get_status(
            room_id=room_id,
            room_name=subscription.room_name,
            days=30,
            threshold=subscription.threshold_kwh,
        )
        remaining = result.get("remaining")
        if remaining is None or float(remaining) > subscription.threshold_kwh:
            return False

        EmailService(EmailConfig.from_env(str(self.settings.env_path))).send_text(
            subscription.email,
            alert_subject(result),
            alert_content(subscription, result, self.settings.base_url),
        )
        self.store.mark_alert_sent(subscription, today)
        return True


def start_alert_worker(project_dir: Path, skip_recent: bool = True) -> threading.Thread:
    runner = AlertRunner(project_dir)
    thread = threading.Thread(
        target=runner.run_forever,
        kwargs={"skip_recent": skip_recent},
        name="alert-worker",
        daemon=True,
    )
    thread.start()
    return thread


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _next_run_at(now: datetime, check_time: str) -> datetime:
    hour, minute = _parse_check_time(check_time)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _parse_check_time(value: str) -> tuple[int, int]:
    parts = value.strip().split(":", 1)
    if len(parts) != 2:
        return 8, 0
    try:
        hour = min(max(int(parts[0]), 0), 23)
        minute = min(max(int(parts[1]), 0), 59)
    except ValueError:
        return 8, 0
    return hour, minute
