"""HTTP_PROXY 环境变量安全校验。

防止 .env 被篡改后将校园网 API 请求重定向到恶意代理。
"""

from __future__ import annotations

import ipaddress
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger("dorm.proxy")

# 内置允许的代理主机范围
_SAFE_HOSTS: list[str] = [
    "127.0.0.1",
    "::1",
    "localhost",
]

_SAFE_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
]


def _parse_proxy_host(proxy_url: str) -> str:
    """从代理 URL 中提取主机名。解析失败返回空字符串。"""
    if not proxy_url or not proxy_url.strip():
        return ""
    url = proxy_url.strip()
    # urlparse 需要 scheme 才能正确解析 hostname，缺 scheme 时手动补
    if "://" not in url:
        url = "http://" + url
    try:
        parsed = urlparse(url)
        return parsed.hostname or ""
    except Exception:
        return ""


def is_safe_proxy_url(proxy_url: str, extra_hosts: str | None = None) -> bool:
    """校验代理 URL 的主机名是否在白名单中。

    空字符串视为安全（表示不使用代理）。
    """
    host = _parse_proxy_host(proxy_url)
    if not host:
        return True  # 空 / 未设置 → 直连，安全

    # 精确匹配
    if host in _SAFE_HOSTS:
        return True

    # IP 网段匹配
    try:
        addr = ipaddress.ip_address(host)
        for network in _SAFE_NETWORKS:
            if addr in network:
                return True
    except ValueError:
        pass  # 非 IP 地址（如域名）

    # 环境变量自定义白名单
    allowed_hosts = extra_hosts or os.getenv("ALLOWED_PROXY_HOSTS", "")
    if allowed_hosts:
        for entry in allowed_hosts.split(","):
            entry = entry.strip()
            if entry and entry == host:
                return True

    return False


def get_safe_proxy() -> str:
    """安全读取 HTTP_PROXY 环境变量。

    代理 URL 在白名单内 → 正常返回。
    代理 URL 不在白名单内 → 记录 WARNING，返回空字符串（回退直连）。
    未设置 → 返回空字符串。
    """
    proxy_url = (
        os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
    ).strip()
    if not proxy_url:
        return ""

    if is_safe_proxy_url(proxy_url):
        logger.debug("Using HTTP_PROXY=%s", proxy_url)
        return proxy_url

    host = _parse_proxy_host(proxy_url)
    logger.warning(
        "HTTP_PROXY rejected (host %r not in allowlist), falling back to direct connection",
        host or proxy_url,
    )
    return ""
