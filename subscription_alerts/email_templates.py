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


def daily_report_subject(subscription: Subscription) -> str:
    from datetime import date

    return (
        f"每日电费报告：{subscription.building_name} {subscription.room_name}"
        f" · {date.today().isoformat()}"
    )


def daily_report_content(
    subscription: Subscription,
    result: dict[str, Any],
    base_url: str,
) -> str:
    remaining = result.get("remaining", "?")
    total_used = result.get("total_used_kwh", "?")
    daily_avg = result.get("daily_avg_kwh", "?")
    est_days = result.get("est_days_left", "?")
    last_record = result.get("last_record") or "暂无"
    threshold = subscription.threshold_kwh

    lines = [
        "你好，以下是您订阅宿舍的电费使用情况汇总：",
        "",
        f"宿舍：{subscription.campus_name} {subscription.building_name} {subscription.room_name}",
        f"统计日期：{last_record}",
        "",
        f"当前余额：{remaining} kWh",
        f"近30日用电总量：{total_used} kWh",
        f"日均耗电：{daily_avg} kWh",
        f"预估剩馀天数：{int(est_days) if isinstance(est_days, (int, float)) and est_days > 0 else '?'} 天",
        f"预警阈值：{threshold:g} kWh",
        "",
    ]

    # 根据余额情况给出提示
    rem_val = float(remaining) if isinstance(remaining, (int, float)) else None
    if rem_val is not None:
        if rem_val <= threshold:
            lines.append("⚠️ 当前余额已低于您的预警阈值，请注意及时充值。")
        elif rem_val <= threshold * 1.5:
            lines.append("💡 余额接近预警线，建议您近期留意用电情况。")
        else:
            lines.append("✅ 余额充足，请放心使用。")
    lines.append("")

    # 附趋势概览（如果有数据的话）
    trend = result.get("trend")
    if trend and isinstance(trend, list):
        recent = trend[-7:]  # 最近7天
        lines.append("近7日余额走势：")
        for entry in recent:
            d = entry.get("date", "")
            r = entry.get("remaining", "?")
            u = entry.get("daily_used_kwh", "-")
            lines.append(f"  {d}  余额 {r} kWh  当日用电 {u} kWh")
        lines.append("")

    # 附加链接
    link_lines = []
    if base_url:
        link_lines.append(f"查看实时详情：{base_url.rstrip('/')}")
        link_lines.append(
            f"取消日报订阅：{base_url.rstrip('/')}/api/unsubscribe?token={subscription.unsubscribe_token}"
        )
    if link_lines:
        lines.extend(link_lines)

    return "\n".join(lines)
