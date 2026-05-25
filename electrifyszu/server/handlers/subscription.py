"""POST /api/subscriptions, verify, unsubscribe — subscription flow handlers."""

from __future__ import annotations

import logging
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlencode

from electrifyszu.config import DormConfig as Config
from electrifyszu.subscription.alerts import AlertSettings
from electrifyszu.subscription.email_service import EmailDeliveryError
from electrifyszu.subscription.store import SubscriptionStore
from electrifyszu.subscription.unsubscribe import unsubscribe_subscription
from electrifyszu.subscription.verification import create_pending_subscription, verify_subscription
from electrifyszu.server.handlers.types import (
    ENV_FILE,
    RequestError,
    query_value,
    read_request_data,
    redirect_to,
    send_error,
    send_json,
    truthy,
)

ROOT = ENV_FILE.parent

logger = logging.getLogger("server")


def handle_subscription_create(handler: BaseHTTPRequestHandler) -> None:
    try:
        config = Config.from_env(str(ENV_FILE))
        settings = AlertSettings.from_env(ROOT)
        store = SubscriptionStore(settings.csv_path)
        try:
            data = read_request_data(handler)
        except RequestError:
            return
        result = create_pending_subscription(
            store=store,
            values={
                "email": data.get("email", ""),
                "client": data.get("client", "") or config.client,
                "campus_name": data.get("campusName", "") or config.campus_name,
                "building_id": data.get("buildingId", "") or config.building_id,
                "building_name": data.get("buildingName", "") or config.building_name,
                "room_name": data.get("roomName", "") or config.room_name,
                "threshold_kwh": data.get("thresholdKwh", str(config.low_power_threshold)),
                "alert_enabled": data.get("alertEnabled", True),
                "daily_report_enabled": data.get("dailyReportEnabled", False),
            },
            default_threshold=config.low_power_threshold,
            base_url=settings.base_url,
            env_path=settings.env_path,
            request_base_url=_request_base_url(handler),
        )
        subscription = result.subscription
        send_json(
            handler,
            {
                "ok": True,
                "data": {
                    "email": subscription.email,
                    "campus_name": subscription.campus_name,
                    "building_name": subscription.building_name,
                    "room_name": subscription.room_name,
                    "threshold_kwh": subscription.threshold_kwh,
                    "alert_enabled": subscription.alert_enabled,
                    "daily_report_enabled": subscription.daily_report_enabled,
                    "verified": subscription.verified,
                },
                "message": (
                    "验证邮件已发送，请点击邮件中的确认链接后启用订阅。"
                    if result.verification_required
                    else "该邮箱订阅已生效。余额低于阈值时，系统每天最多发送一次预警邮件。"
                ),
                "verification_required": result.verification_required,
            },
            status=201,
        )
    except ValueError as exc:
        msg = str(exc)
        if "邮箱" in msg:
            code = "INVALID_EMAIL"
        elif "缺少" in msg:
            code = "MISSING_FIELD"
        elif "阈值" in msg:
            code = "INVALID_THRESHOLD"
        else:
            code = "INVALID_INPUT"
        send_error(handler, code, msg, status=400)
    except EmailDeliveryError as exc:
        send_error(
            handler, "EMAIL_DELIVERY_FAILED", str(exc),
            "验证邮件发送失败，订阅已保存但暂未生效。请联系管理员检查SMTP配置。",
            status=502,
        )
    except Exception as exc:
        send_error(
            handler, "INTERNAL_ERROR", str(exc),
            "订阅保存失败，请稍后重试或联系管理员。", status=500,
        )


def handle_subscription_verify(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    settings = AlertSettings.from_env(ROOT)
    token = query_value(query, "token")
    status, subscription = verify_subscription(SubscriptionStore(settings.csv_path), token)
    if status in ("verified", "already_verified"):
        params = {"notice": status}
        if subscription:
            params["email"] = subscription.email
            params["campus"] = subscription.campus_name
            params["building"] = subscription.building_name
            params["room"] = subscription.room_name
        redirect_to(handler, _dashboard_url(params))
        return
    if status == "expired":
        redirect_to(handler, _dashboard_url({"notice": "verify_expired"}))
        return
    redirect_to(handler, _dashboard_url({"notice": "verify_invalid"}))


def handle_unsubscribe(handler: BaseHTTPRequestHandler, query: dict[str, list[str]]) -> None:
    settings = AlertSettings.from_env(ROOT)
    token = query_value(query, "token")
    status, subscription = unsubscribe_subscription(SubscriptionStore(settings.csv_path), token)
    if status in ("unsubscribed", "already_unsubscribed"):
        params = {"notice": status}
        if subscription:
            params["email"] = subscription.email
            params["campus"] = subscription.campus_name
            params["building"] = subscription.building_name
            params["room"] = subscription.room_name
        redirect_to(handler, _dashboard_url(params))
        return
    redirect_to(handler, _dashboard_url({"notice": "unsubscribe_invalid"}))


def handle_alert_check(handler: BaseHTTPRequestHandler) -> None:
    try:
        data = read_request_data(handler)
    except RequestError:
        return
    skip_recent = truthy(data.get("skipRecent"), default=True)
    from electrifyszu.subscription.alerts import AlertRunner
    stats = AlertRunner(ROOT).run_once(skip_recent=skip_recent)
    send_json(handler, {"ok": True, "data": stats})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _request_base_url(handler: BaseHTTPRequestHandler) -> str:
    import os
    from electrifyszu.config import load_dotenv
    from urllib.parse import urlparse

    load_dotenv(str(ENV_FILE))
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip()
    if _valid_public_base_url(public_base_url):
        return public_base_url.rstrip("/")
    host = handler.headers.get("Host", "127.0.0.1:8000").strip() or "127.0.0.1:8000"
    parsed = urlparse(f"//{host}")
    hostname = (parsed.hostname or "").lower()
    if hostname not in {"127.0.0.1", "localhost", "::1"}:
        host = "127.0.0.1:8000"
    scheme = "https" if handler.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
    return f"{scheme}://{host}"


def _valid_public_base_url(value: str) -> bool:
    from urllib.parse import urlparse
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _dashboard_url(params: dict[str, str]) -> str:
    return f"/?{urlencode(params)}"
