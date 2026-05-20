from __future__ import annotations

import csv
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.api import DormApi
from src.config import Config, _load_dotenv
from src.discover import discover_room_id

from .email_service import EmailConfig, EmailService

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CSV_FIELDS = [
    "email",
    "client",
    "campus_name",
    "building_id",
    "building_name",
    "room_name",
    "threshold_kwh",
    "enabled",
    "created_at",
    "updated_at",
    "last_alert_date",
    "unsubscribe_token",
]
_STORE_LOCKS: dict[Path, threading.Lock] = {}
_STORE_LOCKS_LOCK = threading.Lock()


@dataclass
class Subscription:
    email: str
    client: str
    campus_name: str
    building_id: str
    building_name: str
    room_name: str
    threshold_kwh: float
    enabled: bool
    created_at: str
    updated_at: str
    last_alert_date: str
    unsubscribe_token: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.email.strip().lower(),
            self.client.strip(),
            self.building_id.strip(),
            self.room_name.strip(),
        )

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Subscription":
        return cls(
            email=row.get("email", "").strip(),
            client=row.get("client", "").strip(),
            campus_name=row.get("campus_name", "").strip(),
            building_id=row.get("building_id", "").strip(),
            building_name=row.get("building_name", "").strip(),
            room_name=row.get("room_name", "").strip(),
            threshold_kwh=_to_float(row.get("threshold_kwh"), 20.0),
            enabled=_to_bool(row.get("enabled"), True),
            created_at=row.get("created_at", "").strip(),
            updated_at=row.get("updated_at", "").strip(),
            last_alert_date=row.get("last_alert_date", "").strip(),
            unsubscribe_token=row.get("unsubscribe_token", "").strip(),
        )

    def to_row(self) -> dict[str, str]:
        return {
            "email": self.email,
            "client": self.client,
            "campus_name": self.campus_name,
            "building_id": self.building_id,
            "building_name": self.building_name,
            "room_name": self.room_name,
            "threshold_kwh": f"{self.threshold_kwh:g}",
            "enabled": "true" if self.enabled else "false",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_alert_date": self.last_alert_date,
            "unsubscribe_token": self.unsubscribe_token,
        }


class SubscriptionStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self._lock = _store_lock(self.path)

    def upsert(self, values: dict[str, Any], default_threshold: float) -> Subscription:
        subscription = build_subscription(values, default_threshold)
        with self._lock:
            rows = self.list_all()
            by_key = {row.key: index for index, row in enumerate(rows)}
            existing_index = by_key.get(subscription.key)
            if existing_index is None:
                rows.append(subscription)
            else:
                existing = rows[existing_index]
                subscription.created_at = existing.created_at
                subscription.last_alert_date = existing.last_alert_date
                subscription.unsubscribe_token = (
                    existing.unsubscribe_token or subscription.unsubscribe_token
                )
                rows[existing_index] = subscription
            self._write(rows)
        return subscription

    def list_all(self) -> list[Subscription]:
        if not self.path.is_file():
            return []
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return [
                subscription
                for subscription in (Subscription.from_row(row) for row in reader)
                if subscription.email
            ]

    def list_enabled(self) -> list[Subscription]:
        return [item for item in self.list_all() if item.enabled]

    def mark_alert_sent(self, subscription: Subscription, alert_date: str) -> None:
        with self._lock:
            rows = self.list_all()
            for row in rows:
                if row.key == subscription.key:
                    row.last_alert_date = alert_date
                    row.updated_at = _now_iso()
                    break
            self._write(rows)

    def unsubscribe(self, token: str) -> bool:
        token = token.strip()
        if not token:
            return False
        changed = False
        with self._lock:
            rows = self.list_all()
            for row in rows:
                if secrets.compare_digest(row.unsubscribe_token, token):
                    row.enabled = False
                    row.updated_at = _now_iso()
                    changed = True
                    break
            if changed:
                self._write(rows)
        return changed

    def _write(self, rows: list[Subscription]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_row())
        temp_path.replace(self.path)


def build_subscription(values: dict[str, Any], default_threshold: float) -> Subscription:
    email = str(values.get("email", "")).strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise ValueError("请输入有效的邮箱地址。")

    required = {
        "client": "校区网络参数",
        "campus_name": "校区",
        "building_id": "楼栋 ID",
        "building_name": "楼栋",
        "room_name": "房间号",
    }
    cleaned: dict[str, str] = {}
    for key, label in required.items():
        value = str(values.get(key, "")).strip()
        if not value:
            raise ValueError(f"缺少{label}。")
        cleaned[key] = value

    threshold = _to_float(values.get("threshold_kwh"), default_threshold)
    if threshold <= 0:
        raise ValueError("预警阈值必须大于 0。")

    now = _now_iso()
    return Subscription(
        email=email,
        client=cleaned["client"],
        campus_name=cleaned["campus_name"],
        building_id=cleaned["building_id"],
        building_name=cleaned["building_name"],
        room_name=cleaned["room_name"],
        threshold_kwh=threshold,
        enabled=True,
        created_at=now,
        updated_at=now,
        last_alert_date="",
        unsubscribe_token=secrets.token_urlsafe(24),
    )


def _store_lock(path: Path) -> threading.Lock:
    with _STORE_LOCKS_LOCK:
        lock = _STORE_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _STORE_LOCKS[path] = lock
        return lock


@dataclass(frozen=True)
class AlertSettings:
    csv_path: Path
    check_time: str
    loop_interval_seconds: int
    base_url: str
    env_path: Path

    @classmethod
    def from_env(cls, monitor_dir: Path) -> "AlertSettings":
        env_path = monitor_dir / ".env"
        _load_dotenv(str(env_path))
        default_csv = monitor_dir / "data" / "subscriptions.csv"
        csv_path = Path(_env("SUBSCRIPTIONS_CSV", str(default_csv)))
        if not csv_path.is_absolute():
            csv_path = monitor_dir / csv_path
        return cls(
            csv_path=csv_path,
            check_time=_env("ALERT_CHECK_TIME", "08:00"),
            loop_interval_seconds=max(int(_env("ALERT_LOOP_INTERVAL", "300")), 30),
            base_url=_env("PUBLIC_BASE_URL", ""),
            env_path=env_path,
        )


class AlertRunner:
    def __init__(self, monitor_dir: Path):
        self.monitor_dir = monitor_dir
        self.settings = AlertSettings.from_env(monitor_dir)
        self.store = SubscriptionStore(self.settings.csv_path)

    def run_once(self) -> dict[str, int]:
        today = date.today().isoformat()
        stats = {"checked": 0, "sent": 0, "skipped": 0, "failed": 0}
        for subscription in self.store.list_enabled():
            stats["checked"] += 1
            try:
                if subscription.last_alert_date == today:
                    stats["skipped"] += 1
                    continue
                sent = self._check_subscription(subscription, today)
                if sent:
                    stats["sent"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as exc:
                stats["failed"] += 1
                print(
                    "[alert] failed "
                    f"{subscription.email} {subscription.building_name} "
                    f"{subscription.room_name}: {exc}"
                )
        return stats

    def run_forever(self) -> None:
        print(
            "[alert] daily subscription worker started; "
            f"check_time={self.settings.check_time}, csv={self.settings.csv_path}"
        )
        while True:
            now = datetime.now()
            next_run = _next_run_at(now, self.settings.check_time)
            sleep_seconds = max((next_run - now).total_seconds(), 1)
            time.sleep(min(sleep_seconds, self.settings.loop_interval_seconds))
            if datetime.now() >= next_run:
                stats = self.run_once()
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
            _alert_subject(result),
            _alert_content(subscription, result, self.settings.base_url),
        )
        self.store.mark_alert_sent(subscription, today)
        return True


def start_alert_worker(monitor_dir: Path) -> threading.Thread:
    runner = AlertRunner(monitor_dir)
    thread = threading.Thread(target=runner.run_forever, name="alert-worker", daemon=True)
    thread.start()
    return thread


def _alert_subject(result: dict[str, Any]) -> str:
    room_name = result.get("room_name", "")
    remaining = result.get("remaining", "?")
    return f"电费预警：{room_name} 当前余额 {remaining} kWh"


def _alert_content(
    subscription: Subscription,
    result: dict[str, Any],
    base_url: str,
) -> str:
    remaining = result.get("remaining", "?")
    last_record = result.get("last_record") or "暂无"
    status = result.get("status") or "low"
    lines = [
        "您好，您订阅的宿舍电费余额已低于预警阈值，请及时关注或充值。",
        "",
        f"宿舍：{subscription.campus_name} {subscription.building_name} {subscription.room_name}",
        f"当前余额：{remaining} kWh",
        f"预警阈值：{subscription.threshold_kwh:g} kWh",
        f"预警状态：{status}",
        f"最近记录：{last_record}",
    ]
    if base_url:
        lines.extend(
            [
                "",
                "如需取消提醒，请打开：",
                f"{base_url.rstrip('/')}/api/unsubscribe?token={subscription.unsubscribe_token}",
            ]
        )
    return "\n".join(lines)


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip() or default


def _next_run_at(now: datetime, check_time: str) -> datetime:
    hour, minute = _parse_check_time(check_time)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


def _parse_check_time(value: str) -> tuple[int, int]:
    match = re.match(r"^(\d{1,2}):(\d{2})$", value.strip())
    if not match:
        return 8, 0
    hour = min(max(int(match.group(1)), 0), 23)
    minute = min(max(int(match.group(2)), 0), 59)
    return hour, minute


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()
