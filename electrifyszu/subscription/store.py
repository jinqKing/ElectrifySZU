from __future__ import annotations

import csv
import os
import re
import secrets
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
MAX_EMAIL_LENGTH = 254
MAX_CLIENT_LENGTH = 64
MAX_BUILDING_ID_LENGTH = 32
MAX_NAME_LENGTH = 80
MAX_ROOM_NAME_LENGTH = 32
MAX_THRESHOLD_KWH = 10000.0
CSV_FIELDS = [
    "email",
    "client",
    "campus_name",
    "building_id",
    "building_name",
    "room_name",
    "threshold_kwh",
    "alert_enabled",
    "daily_report_enabled",
    "enabled",
    "verified",
    "created_at",
    "updated_at",
    "verified_at",
    "verification_token",
    "verification_token_expires_at",
    "verification_sent_at",
    "last_alert_date",
    "last_daily_report_date",
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
    alert_enabled: bool
    daily_report_enabled: bool
    enabled: bool
    verified: bool
    created_at: str
    updated_at: str
    verified_at: str
    verification_token: str
    verification_token_expires_at: str
    verification_sent_at: str
    last_alert_date: str
    last_daily_report_date: str
    unsubscribe_token: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.email.strip().lower(),
            self.client.strip(),
            self.building_id.strip(),
            self.room_name.strip(),
        )

    @property
    def is_active(self) -> bool:
        return self.enabled and self.verified

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
            alert_enabled=_to_bool(row.get("alert_enabled"), True),
            daily_report_enabled=_to_bool(row.get("daily_report_enabled"), False),
            enabled=_to_bool(row.get("enabled"), True),
            verified=_row_verified(row),
            created_at=row.get("created_at", "").strip(),
            updated_at=row.get("updated_at", "").strip(),
            verified_at=row.get("verified_at", "").strip(),
            verification_token=row.get("verification_token", "").strip(),
            verification_token_expires_at=row.get("verification_token_expires_at", "").strip(),
            verification_sent_at=row.get("verification_sent_at", "").strip(),
            last_alert_date=row.get("last_alert_date", "").strip(),
            last_daily_report_date=row.get("last_daily_report_date", "").strip(),
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
            "alert_enabled": "true" if self.alert_enabled else "false",
            "daily_report_enabled": "true" if self.daily_report_enabled else "false",
            "enabled": "true" if self.enabled else "false",
            "verified": "true" if self.verified else "false",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "verified_at": self.verified_at,
            "verification_token": self.verification_token,
            "verification_token_expires_at": self.verification_token_expires_at,
            "verification_sent_at": self.verification_sent_at,
            "last_alert_date": self.last_alert_date,
            "last_daily_report_date": self.last_daily_report_date,
            "unsubscribe_token": self.unsubscribe_token,
        }


@dataclass(frozen=True)
class SubscriptionSaveResult:
    subscription: Subscription
    status: str

    @property
    def verification_required(self) -> bool:
        return self.status == "pending_verification"


class SubscriptionStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self._lock = _store_lock(self.path)

    def save(self, values: dict[str, Any], default_threshold: float) -> SubscriptionSaveResult:
        submitted = build_subscription(values, default_threshold)
        with self._lock:
            rows = self.list_all()
            by_key = {row.key: index for index, row in enumerate(rows)}
            existing_index = by_key.get(submitted.key)
            existing = rows[existing_index] if existing_index is not None else None

            if existing and existing.is_active:
                subscription = merge_active_subscription(existing, submitted)
                rows[existing_index] = subscription
                status = "active"
            else:
                subscription = merge_pending_subscription(existing, submitted)
                if existing_index is None:
                    rows.append(subscription)
                else:
                    rows[existing_index] = subscription
                status = "pending_verification"

            self._write(rows)
        return SubscriptionSaveResult(subscription=subscription, status=status)

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
        return [item for item in self.list_all() if item.is_active and item.alert_enabled]

    def list_with_reports(self) -> list[Subscription]:
        return [
            item
            for item in self.list_all()
            if item.is_active and item.daily_report_enabled
        ]

    def mark_alert_sent(self, subscription: Subscription, alert_date: str) -> None:
        with self._lock:
            rows = self.list_all()
            for row in rows:
                if row.key == subscription.key:
                    row.last_alert_date = alert_date
                    row.updated_at = now_iso()
                    break
            self._write(rows)

    def mark_daily_report_sent(
        self, subscription: Subscription, report_date: str
    ) -> None:
        with self._lock:
            rows = self.list_all()
            for row in rows:
                if row.key == subscription.key:
                    row.last_daily_report_date = report_date
                    row.updated_at = now_iso()
                    break
            self._write(rows)

    def verify(self, token: str) -> tuple[str, Subscription | None]:
        token = token.strip()
        if not token:
            return "invalid", None

        with self._lock:
            rows = self.list_all()
            for row in rows:
                if not row.verification_token:
                    continue
                if not secrets.compare_digest(row.verification_token, token):
                    continue

                # 检查 token 是否过期
                if row.verification_token_expires_at:
                    try:
                        expires = datetime.fromisoformat(
                            row.verification_token_expires_at
                        )
                        if datetime.now() > expires:
                            row.verification_token = ""
                            row.verification_token_expires_at = ""
                            row.updated_at = now_iso()
                            self._write(rows)
                            return "expired", None
                    except ValueError:
                        pass

                already_verified = row.is_active
                now = now_iso()
                row.enabled = True
                row.verified = True
                row.verified_at = row.verified_at or now
                row.verification_token = ""
                row.verification_token_expires_at = ""
                row.updated_at = now
                self._write(rows)
                return ("already_verified" if already_verified else "verified"), row

        return "invalid", None

    def unsubscribe(self, token: str) -> tuple[str, Subscription | None]:
        token = token.strip()
        if not token:
            return "invalid", None

        with self._lock:
            rows = self.list_all()
            for row in rows:
                if not row.unsubscribe_token:
                    continue
                if secrets.compare_digest(row.unsubscribe_token, token):
                    already_disabled = not row.enabled
                    row.enabled = False
                    row.unsubscribe_token = ""
                    row.updated_at = now_iso()
                    self._write(rows)
                    if already_disabled:
                        return "already_unsubscribed", row
                    return "unsubscribed", row
        return "invalid", None

    def _write(self, rows: list[Subscription]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = ""
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temp_name = file.name
                writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row.to_row())
                file.flush()
                os.fsync(file.fileno())
            Path(temp_name).replace(self.path)
        except Exception:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)
            raise


def build_subscription(values: dict[str, Any], default_threshold: float) -> Subscription:
    email = str(values.get("email", "")).strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
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

    if any(CONTROL_CHAR_PATTERN.search(value) for value in cleaned.values()):
        raise ValueError("输入包含非法控制字符。")
    if any(ch.isspace() for ch in cleaned["client"]) or len(cleaned["client"]) > MAX_CLIENT_LENGTH:
        raise ValueError("校区网络参数格式不正确。")
    if any(ch.isspace() for ch in cleaned["building_id"]) or len(cleaned["building_id"]) > MAX_BUILDING_ID_LENGTH:
        raise ValueError("楼栋 ID 格式不正确。")
    if len(cleaned["campus_name"]) > MAX_NAME_LENGTH:
        raise ValueError("校区名称过长。")
    if len(cleaned["building_name"]) > MAX_NAME_LENGTH:
        raise ValueError("楼栋名称过长。")
    if len(cleaned["room_name"]) > MAX_ROOM_NAME_LENGTH:
        raise ValueError("房间号过长。")

    threshold = _to_float(values.get("threshold_kwh"), default_threshold)
    if threshold <= 0 or threshold > MAX_THRESHOLD_KWH:
        raise ValueError("预警阈值必须大于 0。")

    now = now_iso()
    return Subscription(
        email=email,
        client=cleaned["client"],
        campus_name=cleaned["campus_name"],
        building_id=cleaned["building_id"],
        building_name=cleaned["building_name"],
        room_name=cleaned["room_name"],
        threshold_kwh=threshold,
        alert_enabled=_to_bool(values.get("alert_enabled"), True),
        daily_report_enabled=_to_bool(values.get("daily_report_enabled"), False),
        enabled=True,
        verified=False,
        created_at=now,
        updated_at=now,
        verified_at="",
        verification_token=secrets.token_urlsafe(24),
        verification_token_expires_at=(
            datetime.now() + timedelta(hours=24)
        ).isoformat(),
        verification_sent_at=now,
        last_alert_date="",
        last_daily_report_date="",
        unsubscribe_token=secrets.token_urlsafe(24),
    )


def merge_active_subscription(existing: Subscription, submitted: Subscription) -> Subscription:
    return Subscription(
        email=submitted.email,
        client=submitted.client,
        campus_name=submitted.campus_name,
        building_id=submitted.building_id,
        building_name=submitted.building_name,
        room_name=submitted.room_name,
        threshold_kwh=submitted.threshold_kwh,
        alert_enabled=submitted.alert_enabled,
        daily_report_enabled=submitted.daily_report_enabled,
        enabled=True,
        verified=True,
        created_at=existing.created_at or submitted.created_at,
        updated_at=now_iso(),
        verified_at=existing.verified_at or existing.created_at or submitted.created_at,
        verification_token=(
            existing.verification_token
            if existing.verification_token
            else ("" if existing.verified else submitted.verification_token)
        ),
        verification_token_expires_at=(
            existing.verification_token_expires_at
        ),
        verification_sent_at=existing.verification_sent_at,
        last_alert_date=existing.last_alert_date,
        last_daily_report_date=existing.last_daily_report_date,
        unsubscribe_token=existing.unsubscribe_token or submitted.unsubscribe_token,
    )


def merge_pending_subscription(
    existing: Subscription | None,
    submitted: Subscription,
) -> Subscription:
    now = now_iso()
    return Subscription(
        email=submitted.email,
        client=submitted.client,
        campus_name=submitted.campus_name,
        building_id=submitted.building_id,
        building_name=submitted.building_name,
        room_name=submitted.room_name,
        threshold_kwh=submitted.threshold_kwh,
        alert_enabled=submitted.alert_enabled,
        daily_report_enabled=submitted.daily_report_enabled,
        enabled=True,
        verified=False,
        created_at=existing.created_at if existing else submitted.created_at,
        updated_at=now,
        verified_at="",
        verification_token=secrets.token_urlsafe(24),
        verification_token_expires_at=(
            datetime.now() + timedelta(hours=24)
        ).isoformat(),
        verification_sent_at=now,
        last_alert_date=existing.last_alert_date if existing else "",
        last_daily_report_date=(
            existing.last_daily_report_date if existing else ""
        ),
        unsubscribe_token=(
            existing.unsubscribe_token
            if existing and existing.unsubscribe_token
            else submitted.unsubscribe_token
        ),
    )


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _store_lock(path: Path) -> threading.Lock:
    with _STORE_LOCKS_LOCK:
        lock = _STORE_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _STORE_LOCKS[path] = lock
        return lock


def _row_verified(row: dict[str, str]) -> bool:
    raw_verified = row.get("verified")
    if raw_verified not in {None, ""}:
        return _to_bool(raw_verified, False)
    if row.get("verified_at", "").strip():
        return True
    return not row.get("verification_token", "").strip() and not row.get(
        "verification_sent_at", ""
    ).strip()


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
