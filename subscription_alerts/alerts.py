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
from .email_templates import (
    alert_content,
    alert_subject,
    daily_report_content,
    daily_report_subject,
)
from .store import Subscription, SubscriptionStore

_shutdown_event = threading.Event()

@dataclass(frozen=True)
class AlertSettings:
    csv_path: Path
    check_time: str
    loop_interval_seconds: int
    base_url: str
    env_path: Path
    mode: str  # "production" or "testing"

    @classmethod
    def from_env(cls, project_dir: Path) -> "AlertSettings":
        env_path = project_dir / ".env"
        _load_dotenv(str(env_path))
        default_csv = project_dir / "data" / "subscriptions.csv"
        csv_path = Path(_env("SUBSCRIPTIONS_CSV", str(default_csv)))
        if not csv_path.is_absolute():
            csv_path = project_dir / csv_path
        mode = _env("ALERT_MODE", "production").strip().lower()
        if mode not in ("production", "testing"):
            mode = "production"
        if mode == "testing":
            interval = max(int(_env("ALERT_TEST_INTERVAL", "300")), 10)
        else:
            interval = max(int(_env("ALERT_LOOP_INTERVAL", "300")), 30)
        return cls(
            csv_path=csv_path,
            check_time=_env("ALERT_CHECK_TIME", "08:00"),
            loop_interval_seconds=interval,
            base_url=_env("PUBLIC_BASE_URL", ""),
            env_path=env_path,
            mode=mode,
        )


class AlertRunner:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.settings = AlertSettings.from_env(project_dir)
        self.store = SubscriptionStore(self.settings.csv_path)

    def run_once(self, skip_recent: bool = True) -> dict[str, int]:
        today = date.today().isoformat()
        force_alert = (
            self.settings.mode == "testing"
            and _env("FORCE_SEND_ALERT", "0").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        force_report = (
            self.settings.mode == "testing"
            and _env("FORCE_SEND_DAILY_REPORT", "0").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        stats = {
            "checked": 0,
            "alerts_sent": 0,
            "reports_sent": 0,
            "skipped": 0,
            "failed": 0,
        }

        # --- Phase A: collect subs needing checks ---
        alert_subs = []
        for sub in self.store.list_enabled():
            if skip_recent and sub.last_alert_date == today:
                stats["skipped"] += 1
                continue
            alert_subs.append(sub)

        report_subs = []
        for sub in self.store.list_with_reports():
            if skip_recent and sub.last_daily_report_date == today:
                stats["skipped"] += 1
                continue
            report_subs.append(sub)

        # Deduplicate rooms across both lists (each room queried once)
        room_keys_seen: set[tuple[str, str]] = set()
        ordered_checks: list[tuple[bool, Subscription]] = []
        for sub in alert_subs:
            rk = (sub.building_id, sub.room_name)
            if rk not in room_keys_seen:
                room_keys_seen.add(rk)
                ordered_checks.append((True, sub))
        for sub in report_subs:
            rk = (sub.building_id, sub.room_name)
            if rk not in room_keys_seen:
                room_keys_seen.add(rk)
                ordered_checks.append((False, sub))

        # Track which (email, building, room) combos got an alert mail this run
        # so we don't also send a duplicate report to the same place
        alerted_keys: set[tuple[str, str, str, str]] = set()

        # --- Phase B: fetch data per-room, dispatch per-sub ---
        for want_alert, subscription in ordered_checks:
            stats["checked"] += 1
            try:
                result = self._fetch_room_data(
                    subscription,
                    force=((want_alert and force_alert)
                           or (not want_alert and force_report)),
                )
                if result is None:
                    stats["skipped"] += 1
                    continue

                sub_key = subscription.key

                if want_alert:
                    remaining = result.get("remaining")
                    if remaining is not None and float(remaining) <= subscription.threshold_kwh:
                        self._dispatch_alert(subscription, result, today)
                        stats["alerts_sent"] += 1
                        alerted_keys.add(sub_key)
                    else:
                        stats["skipped"] += 1

                # Report branch: fire unless this exact sub already got an alert
                if subscription.daily_report_enabled and sub_key not in alerted_keys:
                    self._dispatch_report(subscription, result, today)
                    stats["reports_sent"] += 1

            except Exception as exc:
                stats["failed"] += 1
                print(
                    "[alert] failed "
                    f"{subscription.email} {subscription.building_name} "
                    f"{subscription.room_name}: {exc}"
                )

        # Backward compat: expose 'sent' as sum for callers expecting old shape
        stats["sent"] = stats["alerts_sent"] + stats["reports_sent"]
        return stats

    def run_forever(self, skip_recent: bool = True) -> None:
        effective_skip = (
            skip_recent
            if self.settings.mode == "production"
            else _env("SKIP_RECENT", "1").strip().lower() in {"1", "true", "yes", "on"}
        )
        print(
            "[alert] subscription worker started; "
            f"mode={self.settings.mode}, check_time={self.settings.check_time}, "
            f"interval={self.settings.loop_interval_seconds}s, "
            f"effective_skip_recent={effective_skip}, csv={self.settings.csv_path}"
        )
        cycle = 0
        while True:
            if self.settings.mode == "production":
                now = datetime.now()
                next_run = _next_run_at(now, self.settings.check_time)
                sleep_secs = max((next_run - now).total_seconds(), 1)
                if _shutdown_event.wait(timeout=min(sleep_secs, self.settings.loop_interval_seconds)):
                    break
                if datetime.now() >= next_run:
                    cycle += 1
                    stats = self.run_once(skip_recent=effective_skip)
                    print(f"[alert] daily check #{cycle} finished: {stats}")
                    time.sleep(60)
                continue
            cycle += 1
            stats = self.run_once(skip_recent=effective_skip)
            print(f"[alert] cycle #{cycle} finished: {stats}")
            if _shutdown_event.wait(timeout=self.settings.loop_interval_seconds):
                break


    def _fetch_room_data(
        self, subscription: Subscription, *, force: bool = False
    ) -> dict[str, object] | None:
        """Return the room status dict (or None on skip).

        When *force* is True, returns fabricated data without hitting the API.
        """
        if force:
            return {
                "room_name": subscription.room_name,
                "remaining": round(subscription.threshold_kwh * 0.5, 1),
                "last_record": date.today().isoformat(),
                "status": "critical",
                "total_used_kwh": 50.0,
                "daily_avg_kwh": 1.7,
                "est_days_left": 3.0,
                "threshold_kwh": subscription.threshold_kwh,
                "trend": [],
                "recharges": [],
            }

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

        return DormApi(config).get_status(
            room_id=room_id,
            room_name=subscription.room_name,
            days=30,
            threshold=subscription.threshold_kwh,
        )

    def _dispatch_alert(
        self, subscription: Subscription, result: dict[str, object], today: str
    ) -> None:
        EmailService(EmailConfig.from_env(str(self.settings.env_path))).send_text(
            subscription.email,
            alert_subject(result),
            alert_content(subscription, result, self.settings.base_url),
        )
        self.store.mark_alert_sent(subscription, today)

    def _dispatch_report(
        self, subscription: Subscription, result: dict[str, object], today: str
    ) -> None:
        EmailService(EmailConfig.from_env(str(self.settings.env_path))).send_text(
            subscription.email,
            daily_report_subject(subscription),
            daily_report_content(subscription, result, self.settings.base_url),
        )
        self.store.mark_daily_report_sent(subscription, today)


def shutdown_alert_worker() -> None:
    """Signal the alert worker to stop."""
    _shutdown_event.set()


def reset_shutdown_flag() -> None:
    _shutdown_event.clear()


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
