"""Subscription persistence — SQLite-backed store.

Replaces the legacy CSV-based store. Public API is unchanged:
    SubscriptionStore, Subscription, SubscriptionSaveResult,
    build_subscription, merge_active_subscription, merge_pending_subscription.

Internal storage uses the electrifyszu.database module (SQLite, WAL mode).
Migration from legacy CSV happens automatically if needed.
"""

from __future__ import annotations

import csv
import os
import re
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from electrifyszu.database import get_connection, get_db_path, ensure_db, set_db_path

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
MAX_EMAIL_LENGTH = 254
MAX_CLIENT_LENGTH = 64
MAX_BUILDING_ID_LENGTH = 32
MAX_NAME_LENGTH = 80
MAX_ROOM_NAME_LENGTH = 32
MAX_THRESHOLD_KWH = 10000.0

# 默认允许的邮箱域名（可通过环境变量 ALLOWED_EMAIL_DOMAINS 覆盖，逗号分隔）
_DEFAULT_ALLOWED_DOMAINS: frozenset[str] = frozenset({"@email.szu.edu.cn", "@mails.szu.edu.cn"})


def _get_allowed_email_domains() -> frozenset[str]:
    """从环境变量读取允许的邮箱域名集合，留空则使用默认值。"""
    env_val = os.getenv("ALLOWED_EMAIL_DOMAINS")
    if env_val:
        return frozenset(d.strip().lower() for d in env_val.split(",") if d.strip())
    return _DEFAULT_ALLOWED_DOMAINS


# Legacy CSV field list — kept for migration support
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

# Thread lock for table-level operations
_store_lock = threading.Lock()


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
        """Create a Subscription from a legacy CSV dict row."""
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
        """Convert to a legacy CSV dict row (for backward compat)."""
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

    @classmethod
    def from_db_row(cls, row: sqlite3.Row) -> "Subscription":
        """Create a Subscription from a SQLite row."""
        return cls(
            email=row["email"],
            client=row["client"],
            campus_name=row["campus_name"],
            building_id=row["building_id"],
            building_name=row["building_name"],
            room_name=row["room_name"],
            threshold_kwh=row["threshold_kwh"],
            alert_enabled=bool(row["alert_enabled"]),
            daily_report_enabled=bool(row["daily_report_enabled"]),
            enabled=bool(row["enabled"]),
            verified=bool(row["verified"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            verified_at=row["verified_at"] or "",
            verification_token=row["verification_token"] or "",
            verification_token_expires_at=row["verification_token_expires_at"] or "",
            verification_sent_at=row["verification_sent_at"] or "",
            last_alert_date=row["last_alert_date"] or "",
            last_daily_report_date=row["last_daily_report_date"] or "",
            unsubscribe_token=row["unsubscribe_token"] or "",
        )


@dataclass(frozen=True)
class SubscriptionSaveResult:
    subscription: Subscription
    status: str

    @property
    def verification_required(self) -> bool:
        return self.status == "pending_verification"


class SubscriptionStore:
    """SQLite-backed subscription store.

    Accepts a path argument for backward compatibility (legacy CSV path).
    The actual database is stored at data/electrifyszu.db.
    """

    def __init__(self, path: Path | str | None = None):
        # Derive SQLite DB path from the legacy CSV path for backward compat.
        # If a path is provided, place electrifyszu.db in the same directory.
        if path is not None:
            set_db_path(Path(path).parent / "electrifyszu.db")
        ensure_db()

    def save(self, values: dict[str, Any], default_threshold: float) -> SubscriptionSaveResult:
        submitted = build_subscription(values, default_threshold)
        conn = get_connection()

        with _store_lock:
            # Check for existing subscription with same key
            existing = self._find_by_key(conn, submitted.key)

            if existing and existing.is_active:
                subscription = merge_active_subscription(existing, submitted)
                self._update(conn, subscription)
                status = "active"
            else:
                subscription = merge_pending_subscription(existing, submitted)
                if existing:
                    self._update(conn, subscription)
                else:
                    self._insert(conn, subscription)
                status = "pending_verification"

            conn.commit()

        return SubscriptionSaveResult(subscription=subscription, status=status)

    def list_all(self) -> list[Subscription]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM subscriptions ORDER BY email, client, building_id, room_name"
        ).fetchall()
        return [Subscription.from_db_row(r) for r in rows]

    def list_enabled(self) -> list[Subscription]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE enabled=1 AND verified=1 AND alert_enabled=1"
            " ORDER BY email"
        ).fetchall()
        return [Subscription.from_db_row(r) for r in rows]

    def list_with_reports(self) -> list[Subscription]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM subscriptions WHERE enabled=1 AND verified=1 AND daily_report_enabled=1"
            " ORDER BY email"
        ).fetchall()
        return [Subscription.from_db_row(r) for r in rows]

    def mark_alert_sent(self, subscription: Subscription, alert_date: str) -> None:
        conn = get_connection()
        with _store_lock:
            conn.execute(
                "UPDATE subscriptions SET last_alert_date=?, updated_at=? "
                "WHERE email=? AND client=? AND building_id=? AND room_name=?",
                (alert_date, now_iso(),
                 subscription.email, subscription.client,
                 subscription.building_id, subscription.room_name),
            )
            conn.commit()

    def mark_daily_report_sent(self, subscription: Subscription, report_date: str) -> None:
        conn = get_connection()
        with _store_lock:
            conn.execute(
                "UPDATE subscriptions SET last_daily_report_date=?, updated_at=? "
                "WHERE email=? AND client=? AND building_id=? AND room_name=?",
                (report_date, now_iso(),
                 subscription.email, subscription.client,
                 subscription.building_id, subscription.room_name),
            )
            conn.commit()

    def verify(self, token: str) -> tuple[str, Subscription | None]:
        token = token.strip()
        if not token:
            return "invalid", None

        conn = get_connection()
        with _store_lock:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE verification_token=?",
                (token,),
            ).fetchone()

            if row is None:
                return "invalid", None

            sub = Subscription.from_db_row(row)

            # Check expiration
            if sub.verification_token_expires_at:
                try:
                    expires = datetime.fromisoformat(sub.verification_token_expires_at)
                    if datetime.now() > expires:
                        conn.execute(
                            "UPDATE subscriptions SET verification_token='', "
                            "verification_token_expires_at='', updated_at=? "
                            "WHERE email=? AND client=? AND building_id=? AND room_name=?",
                            (now_iso(), sub.email, sub.client, sub.building_id, sub.room_name),
                        )
                        conn.commit()
                        return "expired", None
                except ValueError:
                    pass

            already_verified = sub.is_active
            now = now_iso()
            conn.execute(
                "UPDATE subscriptions SET enabled=1, verified=1, "
                "verified_at=COALESCE(verified_at,?), "
                "verification_token='', verification_token_expires_at='', updated_at=? "
                "WHERE email=? AND client=? AND building_id=? AND room_name=?",
                (now, now, sub.email, sub.client, sub.building_id, sub.room_name),
            )
            conn.commit()

            # Refresh the row to get updated values
            updated = conn.execute(
                "SELECT * FROM subscriptions WHERE email=? AND client=? AND building_id=? AND room_name=?",
                (sub.email, sub.client, sub.building_id, sub.room_name),
            ).fetchone()
            result_sub = Subscription.from_db_row(updated) if updated else sub
            result_sub.verified = True
            result_sub.enabled = True

            return ("already_verified" if already_verified else "verified"), result_sub

    def unsubscribe(self, token: str) -> tuple[str, Subscription | None]:
        token = token.strip()
        if not token:
            return "invalid", None

        conn = get_connection()
        with _store_lock:
            row = conn.execute(
                "SELECT * FROM subscriptions WHERE unsubscribe_token=?",
                (token,),
            ).fetchone()

            if row is None:
                return "invalid", None

            sub = Subscription.from_db_row(row)
            already_disabled = not sub.enabled

            conn.execute(
                "UPDATE subscriptions SET enabled=0, unsubscribe_token='', updated_at=? "
                "WHERE email=? AND client=? AND building_id=? AND room_name=?",
                (now_iso(), sub.email, sub.client, sub.building_id, sub.room_name),
            )
            conn.commit()

            sub.enabled = False
            sub.unsubscribe_token = ""

            if already_disabled:
                return "already_unsubscribed", sub
            return "unsubscribed", sub

    # ── Internal helpers ──────────────────────────────────────────────

    def _find_by_key(self, conn, key: tuple[str, str, str, str]) -> Subscription | None:
        row = conn.execute(
            "SELECT * FROM subscriptions WHERE email=? AND client=? AND building_id=? AND room_name=?",
            key,
        ).fetchone()
        return Subscription.from_db_row(row) if row else None

    def _insert(self, conn, sub: Subscription) -> None:
        conn.execute(
            """INSERT INTO subscriptions
                (email, client, campus_name, building_id, building_name,
                 room_name, threshold_kwh, alert_enabled, daily_report_enabled,
                 enabled, verified, created_at, updated_at, verified_at,
                 verification_token, verification_token_expires_at,
                 verification_sent_at, last_alert_date, last_daily_report_date,
                 unsubscribe_token)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sub.email, sub.client, sub.campus_name,
                sub.building_id, sub.building_name,
                sub.room_name, sub.threshold_kwh,
                1 if sub.alert_enabled else 0,
                1 if sub.daily_report_enabled else 0,
                1 if sub.enabled else 0,
                1 if sub.verified else 0,
                sub.created_at, sub.updated_at,
                sub.verified_at or None,
                sub.verification_token or None,
                sub.verification_token_expires_at or None,
                sub.verification_sent_at or None,
                sub.last_alert_date or "",
                sub.last_daily_report_date or "",
                sub.unsubscribe_token or None,
            ),
        )

    def _update(self, conn, sub: Subscription) -> None:
        conn.execute(
            """UPDATE subscriptions SET
                campus_name=?, building_name=?, room_name=?,
                threshold_kwh=?, alert_enabled=?, daily_report_enabled=?,
                enabled=?, verified=?, updated_at=?, verified_at=?,
                verification_token=?, verification_token_expires_at=?,
                verification_sent_at=?, last_alert_date=?,
                last_daily_report_date=?, unsubscribe_token=?
                WHERE email=? AND client=? AND building_id=? AND room_name=?""",
            (
                sub.campus_name, sub.building_name, sub.room_name,
                sub.threshold_kwh,
                1 if sub.alert_enabled else 0,
                1 if sub.daily_report_enabled else 0,
                1 if sub.enabled else 0,
                1 if sub.verified else 0,
                sub.updated_at, sub.verified_at or None,
                sub.verification_token or None,
                sub.verification_token_expires_at or None,
                sub.verification_sent_at or None,
                sub.last_alert_date or "",
                sub.last_daily_report_date or "",
                sub.unsubscribe_token or None,
                sub.email, sub.client, sub.building_id, sub.room_name,
            ),
        )


# ── Pure functions (unchanged from original) ─────────────────────────────────

def build_subscription(values: dict[str, Any], default_threshold: float) -> Subscription:
    email = str(values.get("email", "")).strip().lower()
    if len(email) > MAX_EMAIL_LENGTH or not EMAIL_PATTERN.match(email):
        raise ValueError("请输入有效的邮箱地址。")

    # 邮箱域名白名单校验
    at_idx = email.find("@")
    if at_idx == -1 or email[at_idx:] not in _get_allowed_email_domains():
        allowed = "、".join(sorted(_get_allowed_email_domains()))
        raise ValueError(f"仅支持 {allowed} 邮箱。")

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


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_verified(row: dict[str, str]) -> bool:
    """Determine if a legacy CSV row represents a verified subscription."""
    raw_verified = row.get("verified")
    if raw_verified not in {None, ""}:
        return _to_bool(raw_verified, False)
    if row.get("verified_at", "").strip():
        return True
    return not row.get("verification_token", "").strip() and not row.get(
        "verification_sent_at", ""
    ).strip()
