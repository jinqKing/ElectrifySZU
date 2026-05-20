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

import sys
import re
import os
from urllib.parse import urljoin, quote

import httpx

from .config import Config

CONFIG = Config.from_env()
BASE_URL = CONFIG.base_url.rstrip("/")


def get_proxy() -> str:
    Config.from_env()
    return os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""


def list_buildings(client_ip: str = "") -> dict:
    """获取楼栋列表，返回 {buildingId: buildingName}"""
    client_ip = client_ip or CONFIG.client
    client = httpx.Client(proxy=get_proxy() or None)
    r = client.get(f"{BASE_URL}/login.do?task=station&client={client_ip}")
    opts = re.findall(rb'<option value="(\d+)">([^<]*)</option>', r.content)
    return {bid.decode(): name.decode("gb2312").strip() for bid, name in opts}


def discover_room_id(building_id: str, room_name: str,
                     client_ip: str = "") -> str | None:
    """
    通过登录表单获取 roomId。

    Args:
        building_id: 楼栋ID (如 "7126")
        room_name:   房间号 (如 "713")
        client_ip:   校区IP

    Returns:
        roomId 字符串，找不到返回 None
    """
    client_ip = client_ip or CONFIG.client
    client = httpx.Client(proxy=get_proxy() or None)

    # Step 1: GET login page
    r = client.get(f"{BASE_URL}/login.do?task=station&client={client_ip}",
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
        urljoin(BASE_URL, action),
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{BASE_URL}/login.do?task=station&client={client_ip}",
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

    if sys.argv[1] == "--list":
        print(f"楼栋列表 (client={CONFIG.client}):\n")
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
        print(f"\n  将以下配置加入 .env:")
        print(f"  DORM_ROOM_ID={room_id}")
        print(f"  DORM_ROOM_NAME={room_name}")
        print(f"  DORM_CLIENT={CONFIG.client}")
    else:
        print(f"\n  [!] 未找到。请确认:")
        print(f"      - buildingId 正确 (用 --list 查看)")
        print(f"      - 房间号存在")


if __name__ == "__main__":
    main()
