#!/usr/bin/env python3
"""
roomId 发现工具

通过模拟登录表单自动获取 roomId。

用法:
  python -m src.discover [building_id] [room_name]
  python -m src.discover 7126 713          # 查找风栀斋 713 的 roomId
  python -m src.discover --list            # 列出所有楼栋

原理:
  1. GET login.do → 获取 JSESSIONID
  2. POST login.do (buildingId + roomName + buildingName)
  3. 解析返回的 selectList 页面 → 提取 <input name="roomId" value="XXXX">
"""

import os
import re
import sys
from urllib.parse import urljoin, quote

import httpx

from electrifyszu.config import DormConfig as Config


def get_proxy() -> str:
    from electrifyszu.dorm.proxy import get_safe_proxy
    return get_safe_proxy()


def _base_url(value: str = "") -> str:
    if value:
        return value.rstrip("/")
    return Config.from_env().base_url.rstrip("/")


def list_buildings(client_ip: str = "", base_url: str = "") -> dict:
    """获取楼栋列表，返回 {buildingId: buildingName}。

    优先从持久化表 building_list 读取；超过 6 小时则重新请求校园 API 并更新。
    """
    config = Config.from_env()
    client_ip = client_ip or config.client

    from electrifyszu.database import ensure_db, get_connection
    from datetime import datetime, timedelta

    ensure_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT updated_at FROM building_list WHERE client=? LIMIT 1",
        (client_ip,),
    ).fetchone()

    stale = True
    if row is not None:
        cutoff = (datetime.now() - timedelta(hours=6)).isoformat()
        stale = row["updated_at"] < cutoff

    if not stale:
        rows = conn.execute(
            "SELECT building_id, building_name FROM building_list WHERE client=?",
            (client_ip,),
        ).fetchall()
        return {r["building_id"]: r["building_name"] for r in rows}

    client = httpx.Client(proxy=get_proxy() or None)
    r = client.get(f"{_base_url(base_url)}/login.do?task=station&client={client_ip}")
    opts = re.findall(rb'<option value="(\d+)">([^<]*)</option>', r.content)
    result = {bid.decode(): name.decode("gb2312").strip() for bid, name in opts}

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for bid, name in result.items():
        conn.execute(
            "INSERT OR REPLACE INTO building_list (client, building_id, building_name, updated_at) VALUES (?,?,?,?)",
            (client_ip, bid, name, now),
        )
    conn.commit()
    return result


def discover_room_id(building_id: str, room_name: str,
                     client_ip: str = "",
                     base_url: str = "") -> str | None:
    """通过登录表单获取 roomId。优先从持久化表 room_mapping 读取。"""
    config = Config.from_env()
    client_ip = client_ip or config.client

    from electrifyszu.database import ensure_db, get_connection

    ensure_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT room_id FROM room_mapping WHERE client=? AND building_id=? AND room_name=?",
        (client_ip, building_id, room_name),
    ).fetchone()
    if row is not None:
        return row["room_id"]

    result = _discover_room_id_impl(building_id, room_name, client_ip, base_url)
    if result is not None:
        conn.execute(
            "INSERT OR IGNORE INTO room_mapping (client, building_id, room_name, room_id) VALUES (?,?,?,?)",
            (client_ip, building_id, room_name, result),
        )
        conn.commit()
    return result


def _discover_room_id_impl(building_id: str, room_name: str,
                           client_ip: str, base_url: str) -> str | None:
    """原始 discover_room_id 实现（直接请求校园 API）。"""
    client = httpx.Client(proxy=get_proxy() or None)
    api_base = _base_url(base_url)

    # Step 1: GET login page
    r = client.get(f"{api_base}/login.do?task=station&client={client_ip}",
                   headers={"User-Agent": "Mozilla/5.0"})

    # 提取 form action 和 building option 文本
    action_m = re.search(rb'action="([^"]+)"', r.content)
    if not action_m:
        return None
    action = action_m.group(1).decode()

    # 查找 buildingId 对应的 option 文本
    opt_m = re.search(
        rf'<option value="{building_id}">([^<]*)</option>'.encode(), r.content)
    if not opt_m:
        # buildingId 不在当前校区的建筑列表中
        return None

    opt_text = opt_m.group(1).decode("gb2312")

    # Step 2: POST 登录表单
    body = "&".join([
        f"client={client_ip}",
        f"buildingId={building_id}",
        "buildingName=" + quote(opt_text.encode("gb2312")),
        f"roomName={room_name}",
        "select=" + quote("查询".encode("gb2312")),
    ]).encode("ascii")

    resp = client.post(
        urljoin(api_base + "/", action),
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{api_base}/login.do?task=station&client={client_ip}",
            "User-Agent": "Mozilla/5.0",
        }
    )

    # Step 3: 从响应中提取 roomId
    html = resp.text
    room_id_m = re.search(
        r'<input[^>]*type="hidden"[^>]*name="roomId"[^>]*value="(\d+)"', html)
    if room_id_m:
        return room_id_m.group(1)
    return None


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print(__doc__)
        return

    config = Config.from_env()

    if sys.argv[1] == "--list":
        print(f"楼栋列表 (client={config.client}):\n")
        buildings = list_buildings()
        for bid, name in buildings.items():
            print(f"  buildingId={bid:>6}    {name}")
        return

    building_id = sys.argv[1]
    room_name = sys.argv[2] if len(sys.argv) > 2 else ""

    if not room_name:
        print("用法: python -m src.discover <building_id> <room_name>")
        print("      python -m src.discover --list")
        return

    print(f"\n查找 buildingId={building_id}, roomName={room_name} ...")
    room_id = discover_room_id(building_id, room_name)

    if room_id:
        print(f"\n  >>> roomId = {room_id} <<<")
        print("\n  将以下配置加入 .env:")
        print(f"  DORM_ROOM_ID={room_id}")
        print(f"  DORM_ROOM_NAME={room_name}")
        print(f"  DORM_CLIENT={config.client}")
    else:
        print("\n  [!] 未找到。请确认:")
        print("      - buildingId 正确 (用 --list 查看)")
        print("      - 房间号存在")


if __name__ == "__main__":
    main()
