from __future__ import annotations

from typing import Any

from .store import Subscription


def verification_subject(subscription: Subscription) -> str:
    return f"请确认 ElectrifySZU 预警订阅：{subscription.room_name}"


def verification_content(subscription: Subscription, confirmation_url: str) -> str:
    return "\n".join(
        [
            "你好，",
            "",
            "我们收到了一个 ElectrifySZU 电费订阅请求。请点击下方链接完成邮箱验证：",
            confirmation_url,
            "",
            f"宿舍：{subscription.campus_name} {subscription.building_name} {subscription.room_name}",
            f"预警阈值：{subscription.threshold_kwh:g} kWh",
            f"订阅电费预警：{'是' if subscription.alert_enabled else '否'}",
            f"每日电费报告：{'是' if subscription.daily_report_enabled else '否'}",
            "",
            "如果这不是你的操作，可以直接忽略这封邮件。",
        ]
    )


def alert_subject(result: dict[str, Any]) -> str:
    room_name = result.get("room_name", "")
    remaining = result.get("remaining", "?")
    return f"电费预警：{room_name} 当前余额 {remaining} kWh"


def alert_content(
    subscription: Subscription,
    result: dict[str, Any],
    base_url: str,
) -> str:
    remaining = result.get("remaining", "?")
    last_record = result.get("last_record") or "暂无"
    status = result.get("status") or "low"
    lines = [
        "你好，您订阅的宿舍电费余额已低于预警阈值，请及时关注或充值。",
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
