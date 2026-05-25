from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from electrifyszu.dorm.api import DormApi
from electrifyszu.config import DormConfig as Config, load_dotenv
from electrifyszu.dorm.discover import discover_room_id

from electrifyszu.subscription.email_service import EmailConfig, EmailDeliveryError, EmailService
from electrifyszu.subscription.email_templates import (
    alert_content,
    alert_subject,
    daily_report_content,
    daily_report_subject,
)
from electrifyszu.subscription.store import Subscription, SubscriptionStore

logger = logging.getLogger("alerts")

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
        load_dotenv(str(env_path))
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

        # --- Phase B: group subs by room key, fetch once per room ---
        # room_map: room_key -> (representative_sub, [alert_subs], [report_subs])
        def room_key(s: Subscription) -> tuple[str, str, str, str]:
            return s.client, s.campus_name, s.building_id, s.room_name
        room_map: dict[
            tuple[str, str, str, str],
            tuple[Subscription, list[Subscription], list[Subscription]],
        ] = {}
        for sub in alert_subs:
            rk = room_key(sub)
            if rk not in room_map:
                room_map[rk] = (sub, [], [])
            room_map[rk][1].append(sub)
        for sub in report_subs:
            rk = room_key(sub)
            if rk not in room_map:
                room_map[rk] = (sub, [], [])
            room_map[rk][2].append(sub)

        # Track which (email, building, room) combos got an alert mail this run
        # so we don't also send a duplicate report to the same place
        alerted_keys: set[tuple[str, str, str, str]] = set()

        for rk, (rep_sub, alert_subs_for_room, report_subs_for_room) in room_map.items():
            stats["checked"] += 1
            try:
                need_force = (bool(alert_subs_for_room) and force_alert) or (
                    bool(report_subs_for_room) and force_report
                )
                result = self._fetch_room_data(rep_sub, force=need_force)
                if result is None:
                    stats["skipped"] += 1
                    continue

                # Dispatch alerts
                for sub in alert_subs_for_room:
                    remaining = result.get("remaining")
                    if remaining is not None and float(remaining) <= sub.threshold_kwh:
                        self._dispatch_alert(sub, result, today)
                        stats["alerts_sent"] += 1
                        alerted_keys.add(sub.key)
                    else:
                        stats["skipped"] += 1

                # Dispatch reports (skip if same sub already got an alert)
                for sub in report_subs_for_room:
                    if sub.key not in alerted_keys:
                        self._dispatch_report(sub, result, today)
                        stats["reports_sent"] += 1

            except Exception as exc:
                stats["failed"] += 1
                logger.error(
                    "failed room %s %s %s %s: %s",
                    rk[0],
                    rk[1],
                    rk[2],
                    rk[3],
                    exc,
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
        logger.info(
            "subscription worker started; mode=%s, check_time=%s, "
            "interval=%ds, effective_skip_recent=%s, csv=%s",
            self.settings.mode,
            self.settings.check_time,
            self.settings.loop_interval_seconds,
            effective_skip,
            self.settings.csv_path,
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
                    logger.info("daily check #%d finished: %s", cycle, stats)
                    time.sleep(60)
                continue
            cycle += 1
            stats = self.run_once(skip_recent=effective_skip)
            logger.info("cycle #%d finished: %s", cycle, stats)
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
        try:
            EmailService(EmailConfig.from_env(str(self.settings.env_path))).send_text(
                subscription.email,
                alert_subject(result),
                alert_content(subscription, result, self.settings.base_url),
            )
            self.store.mark_alert_sent(subscription, today)
        except EmailDeliveryError as exc:
            logger.error("预警邮件发送失败 %s: %s", subscription.email, exc)
            # 不标记已发送，下次循环会重试
            raise  # 由外层 run_once 统计 failed

    def _dispatch_report(
        self, subscription: Subscription, result: dict[str, object], today: str
    ) -> None:
        try:
            EmailService(EmailConfig.from_env(str(self.settings.env_path))).send_text(
                subscription.email,
                daily_report_subject(subscription),
                daily_report_content(subscription, result, self.settings.base_url),
            )
            self.store.mark_daily_report_sent(subscription, today)
        except EmailDeliveryError as exc:
            logger.error("日报邮件发送失败 %s: %s", subscription.email, exc)
            raise


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
