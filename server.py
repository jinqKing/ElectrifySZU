from __future__ import annotations

import argparse
import hmac
import importlib.util
import json
import logging
import mimetypes
import os
import re
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from log_config import setup_logging

ROOT = Path(__file__).resolve().parent
MONITOR_DIR = ROOT / "room-power-monitor"
APARTMENT_DIR = ROOT / "apartment-power-monitor"
WEB_DIR = ROOT / "web"
BUILDINGS_FILE = MONITOR_DIR / "data" / "buildings.txt"
APARTMENT_BUILDINGS_FILE = APARTMENT_DIR / "data" / "buildings.txt"
LIKES_FILE = ROOT / "data" / "likes.json"
ENV_FILE = ROOT / ".env"
sys.path.insert(0, str(MONITOR_DIR))

logger = logging.getLogger("server")

from src.api import DormApi  # noqa: E402
from src.config import Config, _load_dotenv  # noqa: E402
from src.discover import discover_room_id  # noqa: E402
from src.version import __version__  # noqa: E402
from building_power_ranking.cache import (  # noqa: E402
    build_random_sample_plan,
    cached_ranking_for,
    demo_ranking_from_plan,
    load_ranking_cache,
)
from building_power_ranking.ranking import mask_room_name  # noqa: E402

# 排行缓存（模块加载时预读，避免首次请求的惰性加载开销）
_RANKING_CACHE: dict = {}
_RANKING_CACHE_LOADED: bool = False


def _get_ranking_cache() -> dict:
    global _RANKING_CACHE, _RANKING_CACHE_LOADED
    if not _RANKING_CACHE_LOADED:
        _RANKING_CACHE = load_ranking_cache()
        _RANKING_CACHE_LOADED = True
    return _RANKING_CACHE or {}


# 预加载排行缓存 & mimetypes 数据库，避免首次请求冷启动开销
try:
    _RANKING_CACHE = load_ranking_cache()
    _RANKING_CACHE_LOADED = True
except Exception:
    logger.warning("排行缓存预加载失败，将使用惰性加载")
    _RANKING_CACHE = {}
    _RANKING_CACHE_LOADED = False
mimetypes.guess_type("index.html")
from subscription_alerts.alerts import (
    AlertRunner,
    AlertSettings,
    shutdown_alert_worker,
    start_alert_worker,
)  # noqa: E402
from subscription_alerts.email_service import EmailDeliveryError  # noqa: E402
from subscription_alerts.store import SubscriptionStore  # noqa: E402
from subscription_alerts.unsubscribe import unsubscribe_subscription  # noqa: E402
from subscription_alerts.verification import (  # noqa: E402
    create_pending_subscription,
    verify_subscription,
)

# Import apartment-power-monitor as a proper package (avoids 'src' name conflict)
_APARTMENT_LOADED = False


def _ensure_apartment_loaded() -> None:
    """Load apartment-power-monitor/src as the '_apartment' package with proper relative imports."""
    global _APARTMENT_LOADED
    if _APARTMENT_LOADED:
        return
    src_path = APARTMENT_DIR / "src"
    pkg_name = "_apartment"

    init_path = src_path / "__init__.py"
    if init_path.exists():
        spec = importlib.util.spec_from_file_location(pkg_name, str(init_path))
        pkg = importlib.util.module_from_spec(spec)
        pkg.__path__ = [str(src_path)]
        sys.modules[pkg_name] = pkg
        spec.loader.exec_module(pkg)

    for sub in ["version", "config", "buildings", "api"]:
        file_path = src_path / f"{sub}.py"
        if file_path.exists():
            sub_name = f"{pkg_name}.{sub}"
            spec = importlib.util.spec_from_file_location(sub_name, str(file_path))
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = pkg_name
            sys.modules[sub_name] = mod
            spec.loader.exec_module(mod)

    _APARTMENT_LOADED = True


def _apartment_mod(name: str) -> object:
    """Return a loaded apartment submodule."""
    _ensure_apartment_loaded()
    return sys.modules.get(f"_apartment.{name}")

MAX_REQUEST_BODY_BYTES = 64 * 1024
LIKE_ID_PATTERN = re.compile(r"^svr-[0-9a-f]{16}$")
SENSITIVE_QUERY_KEYS = {"token", "email", "userId", "id"}
# Cached GitHub star count (refreshed hourly)
_GITHUB_STARS_CACHE: dict[str, object] = {}
GITHUB_REPO_SLUG = "jinqKing/ElectrifySZU"
GITHUB_STARS_TTL = 3600  # seconds

ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost", "::1"}


class RequestError(Exception):
    """Raised after an error response has already been sent."""


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = f"ElectrifySZU/{__version__}"

    def do_GET(self) -> None:
        self._request_start = time.time()
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/status":
            self._handle_status(query)
            return
        if parsed.path == "/api/buildings":
            self._handle_buildings()
            return
        if parsed.path == "/api/demo-status":
            self._send_json(demo_status())
            return
        if parsed.path == "/api/building-ranking":
            self._handle_building_ranking(query)
            return
        if parsed.path == "/api/apartment/floors":
            self._handle_apartment_floors(query)
            return
        if parsed.path == "/api/apartment/rooms":
            self._handle_apartment_rooms(query)
            return
        if parsed.path == "/api/unsubscribe":
            self._handle_unsubscribe(query)
            return
        if parsed.path == "/api/subscriptions/verify":
            self._handle_verify_subscription(query)
            return
        if parsed.path == "/api/version":
            self._send_json(
                {"ok": True, "version": __version__, "python": sys.version.split()[0]}
            )
            return
        if parsed.path == "/api/github-stars":
            self._handle_github_stars()
            return
        if parsed.path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "status": "healthy",
                    "version": __version__,
                    "python": sys.version.split()[0],
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return
        if parsed.path == "/api/like/count":
            self._handle_like_count()
            return
        if parsed.path == "/api/like/my":
            self._handle_like_my(query)
            return
        if parsed.path == "/api/stats":
            self._handle_stats()
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        self._request_start = time.time()
        parsed = urlparse(self.path)
        if not self._validate_same_origin():
            self._error("FORBIDDEN_ORIGIN", "Forbidden origin", status=403)
            return
        if parsed.path == "/api/alerts/check":
            self._handle_alert_check()
            return
        if parsed.path == "/api/subscriptions":
            self._handle_subscription()
            return
        if parsed.path == "/api/like/init":
            self._handle_like_init()
            return
        if parsed.path == "/api/like":
            self._handle_like()
            return
        self._error("NOT_FOUND", "Not found", status=404)

    # ── Like endpoints ──────────────────────────────────────────────

    def _handle_like_count(self) -> None:
        with _likes_lock:
            data = _load_likes()
        self._send_json({"ok": True, "count": data["count"]})

    def _handle_like_my(self, query: dict[str, list[str]]) -> None:
        user_id = _query_value(query, "userId")
        if user_id and not _is_valid_like_id(user_id):
            self._error("INVALID_LIKE_ID", "Invalid like id", status=400)
            return
        with _likes_lock:
            data = _load_likes()
            liked = user_id in data["likedIds"]
        self._send_json({"ok": True, "data": {"liked": liked}})

    def _handle_stats(self) -> None:
        with _likes_lock:
            data = _load_likes()
        self._send_json({
            "ok": True,
            "data": {
                "likes": data["count"],
                "users": data.get("totalIssued", 0),
            },
        })

    def _handle_like_init(self) -> None:
        new_id = f"svr-{uuid.uuid4().hex[:16]}"
        with _likes_lock:
            data = _load_likes()
            seen = data.setdefault("seenIds", [])
            seen.append(new_id)
            data["totalIssued"] = len(seen)
            _save_likes(data)
        self._send_json({"ok": True, "id": new_id})

    def _handle_like(self) -> None:
        try:
            body = self._read_request_data()
        except RequestError:
            return
        user_id = body.get("id", "")
        if not isinstance(user_id, str) or not _is_valid_like_id(user_id):
            self._error("INVALID_LIKE_ID", "Invalid like id", status=400)
            return
        with _likes_lock:
            data = _load_likes()
            seen = data.setdefault("seenIds", [])
            if user_id not in seen:
                self._error("UNKNOWN_LIKE_ID", "Unknown like id", status=400)
                return
            if user_id in data["likedIds"]:
                self._send_json({"ok": True, "already_liked": True, "count": data["count"], "users": len(seen)})
                return
            data["likedIds"].append(user_id)
            data["count"] += 1
            _save_likes(data)
        logger.info("Like #%d from %s", data["count"], _safe_like_id(user_id))
        self._send_json({"ok": True, "already_liked": False, "count": data["count"], "users": data.get("totalIssued", 0)})

    def log_message(self, fmt: str, *args: object) -> None:
        """覆写：结构化日志，包含 IP、方法、路径、状态码、耗时。"""
        elapsed = ""
        if hasattr(self, "_request_start"):
            ms = (time.time() - self._request_start) * 1000
            elapsed = f" ({ms:.0f}ms)"
        message = fmt % args if args else fmt
        logger.info(
            "%s - %s%s",
            self.address_string(),
            _redact_access_log(message),
            elapsed,
        )

    def _handle_status(self, query: dict[str, list[str]]) -> None:
        try:
            client = _query_value(query, "client") or ""
            building_id = _query_value(query, "buildingId") or ""
            campus_name = _query_value(query, "campusName") or ""
            building_name = _query_value(query, "buildingName") or ""
            room_name = _query_value(query, "roomName") or ""
            days = int(_query_value(query, "days") or "30")

            # 丽湖校区内，公寓系统楼栋（编码01-06）走 ApartmentPowerApi
            if client == "172.21.101.11" and building_id in ("01", "02", "03", "04", "05", "06"):
                self._handle_apartment_status(building_id, room_name, days)
                return

            config = Config.from_env(str(ENV_FILE))
            config.client = client or config.client
            room_id = discover_room_id(
                building_id=building_id or config.building_id,
                room_name=room_name or config.room_name,
                client_ip=config.client,
                base_url=config.base_url,
            )
            if not room_id:
                raise LookupError(f"未找到 {campus_name} {building_name} {room_name} 房间。")

            result = DormApi(config).get_status(
                room_id=room_id,
                room_name=room_name or config.room_name,
                days=days,
                threshold=config.low_power_threshold,
            )
            result["client"] = client or config.client
            result["campus_name"] = campus_name or config.campus_name
            result["building_id"] = building_id or config.building_id
            result["building_name"] = building_name or config.building_name

            # 楼栋排行百分位 — 与缓存中同楼样本对比
            try:
                ranking_data = cached_ranking_for(
                    _get_ranking_cache(), client=client, building_id=building_id
                )
                if ranking_data and ranking_data.get("ranking"):
                    rows = ranking_data["ranking"]
                    user_total = result.get("total_used_kwh")
                    if user_total is not None:
                        below = sum(
                            1 for r in rows if r["total_used_kwh"] < user_total
                        )
                        total = len(rows)
                        percentile = round(below / total * 100) if total > 0 else 0
                        result["building_percentile"] = percentile
                        result["building_rank"] = below + 1
                        result["building_rank_total"] = total
            except Exception:
                pass  # 无缓存或解析失败时不阻塞

            self._send_json({"ok": True, "data": result})
        except LookupError as exc:
            self._error(
                "ROOM_NOT_FOUND",
                str(exc),
                "请确认校区、楼栋与房间号是否正确。",
                status=502,
            )
        except Exception as exc:
            self._error(
                "CAMPUS_NETWORK_ERROR",
                str(exc),
                "请确认已连接校园网，稍后重试。",
                status=502,
            )

    def _handle_apartment_status(self, building_code: str, room_name: str, days: int) -> None:
        try:
            config_mod = _apartment_mod("config")
            api_mod = _apartment_mod("api")

            apt_config = config_mod.Config.from_env(str(ENV_FILE))
            api = api_mod.ApartmentPowerApi(apt_config)
            result = api.get_status(
                building_code=building_code,
                room_name=room_name,
                days=days,
                threshold=apt_config.low_power_threshold,
            )
            result["client"] = "172.21.101.11"
            result["campus_name"] = "西丽校区"
            result["building_id"] = building_code
            self._send_json({"ok": True, "data": result})
        except LookupError as exc:
            self._error(
                "ROOM_NOT_FOUND",
                str(exc),
                "请确认楼栋与房间号是否正确。",
                status=502,
            )
        except Exception as exc:
            self._error(
                "CAMPUS_NETWORK_ERROR",
                str(exc),
                "请确认已连接校园网，稍后重试。",
                status=502,
            )

    def _handle_building_ranking(self, query: dict[str, list[str]]) -> None:
        """GET /api/building-ranking?client=...&buildingId=... — 返回缓存中的楼栋排行。"""
        try:
            config = Config.from_env(str(ENV_FILE))
            client = _query_value(query, "client") or config.client
            building_id = _query_value(query, "buildingId") or config.building_id

            result = cached_ranking_for(_get_ranking_cache(), client=client, building_id=building_id)
            if result is None:
                self._send_json(
                    {"ok": False, "error": "未找到该楼栋的本地排行缓存。"},
                    status=404,
                )
                return
            self._send_json({"ok": True, "data": result})
        except Exception as exc:
            self._send_json(
                {"ok": False, "error": str(exc)},
                status=502,
            )

    def _handle_apartment_floors(self, query: dict[str, list[str]]) -> None:
        try:
            building_code = _query_value(query, "building") or ""
            buildings_mod = _apartment_mod("buildings")
            building = buildings_mod.get_building(building_code)
            floors = [
                {"code": f"{building.code}{f:02d}", "label": building.floor_label(f)}
                for f in building.floors
            ]
            self._send_json({"ok": True, "data": {"building_code": building.code, "building_name": building.name, "floors": floors}})
        except LookupError as exc:
            self._error("BUILDING_NOT_FOUND", str(exc), status=404)
        except Exception as exc:
            self._error("ERROR", str(exc), status=500)

    def _handle_apartment_rooms(self, query: dict[str, list[str]]) -> None:
        try:
            building_code = _query_value(query, "building") or ""
            floor_code = _query_value(query, "floor") or ""
            buildings_mod = _apartment_mod("buildings")
            building = buildings_mod.get_building(building_code)
            # floor_code format: building_code + floor_number (e.g. "0105")
            floor_num = int(floor_code[-2:]) if len(floor_code) >= 2 else 0
            rooms = [
                {"code": rc, "label": rl}
                for rc, rl in building.iter_rooms()
                if rc[:4] == floor_code[:4]
            ]
            self._send_json({"ok": True, "data": {"building_code": building.code, "building_name": building.name, "floor_code": floor_code, "rooms": rooms}})
        except LookupError as exc:
            self._error("BUILDING_NOT_FOUND", str(exc), status=404)
        except Exception as exc:
            self._error("ERROR", str(exc), status=500)

    def _handle_buildings(self) -> None:
        config = Config.from_env(str(ENV_FILE))
        data = merge_campuses(default_campuses(config), load_buildings_file())
        # 公寓6栋楼归入丽湖校区 (client=172.21.101.11)，前端无感知
        _merge_apartment_into_lihu(data)
        self._send_json({"ok": True, "data": data})

    def _handle_subscription(self) -> None:
        try:
            config = Config.from_env(str(ENV_FILE))
            settings = AlertSettings.from_env(ROOT)
            store = SubscriptionStore(settings.csv_path)
            try:
                data = self._read_request_data()
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
                    "threshold_kwh": data.get(
                        "thresholdKwh",
                        str(config.low_power_threshold),
                    ),
                    "alert_enabled": data.get("alertEnabled", True),
                    "daily_report_enabled": data.get("dailyReportEnabled", False),
                },
                default_threshold=config.low_power_threshold,
                base_url=settings.base_url,
                env_path=settings.env_path,
                request_base_url=self._request_base_url(),
            )
            subscription = result.subscription

            self._send_json(
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
            self._error(code, msg, status=400)
        except EmailDeliveryError as exc:
            self._error(
                "EMAIL_DELIVERY_FAILED",
                str(exc),
                "验证邮件发送失败，订阅已保存但暂未生效。请联系管理员检查SMTP配置。",
                status=502,
            )
        except Exception as exc:
            self._error(
                "INTERNAL_ERROR",
                str(exc),
                "订阅保存失败，请稍后重试或联系管理员。",
                status=500,
            )

    def _handle_verify_subscription(self, query: dict[str, list[str]]) -> None:
        settings = AlertSettings.from_env(ROOT)
        token = _query_value(query, "token")
        status, subscription = verify_subscription(SubscriptionStore(settings.csv_path), token)
        if status == "verified":
            params = {"notice": "verified"}
            if subscription:
                params["email"] = subscription.email
                params["campus"] = subscription.campus_name
                params["building"] = subscription.building_name
                params["room"] = subscription.room_name
            self._redirect_to_dashboard(params)
            return
        if status == "already_verified":
            params = {"notice": "already_verified"}
            if subscription:
                params["email"] = subscription.email
                params["campus"] = subscription.campus_name
                params["building"] = subscription.building_name
                params["room"] = subscription.room_name
            self._redirect_to_dashboard(params)
            return
        if status == "expired":
            self._redirect_to_dashboard({"notice": "verify_expired"})
            return
        self._redirect_to_dashboard({"notice": "verify_invalid"})

    def _handle_github_stars(self) -> None:
        global _GITHUB_STARS_CACHE
        ts = _GITHUB_STARS_CACHE.get("ts", 0)
        if time.time() - ts < GITHUB_STARS_TTL:
            self._send_json({"ok": True, "stars": _GITHUB_STARS_CACHE["stars"]})
            return
        url = f"https://api.github.com/repos/{GITHUB_REPO_SLUG}"
        try:
            import httpx as _hx
            resp = _hx.get(url, timeout=5)
            stars = resp.json().get("stargazers_count", 0)
        except Exception:
            stars = _GITHUB_STARS_CACHE.get("stars", 0)
        _GITHUB_STARS_CACHE.update(stars=int(stars), ts=time.time())
        self._send_json({"ok": True, "stars": _GITHUB_STARS_CACHE["stars"]})

    def _handle_unsubscribe(self, query: dict[str, list[str]]) -> None:
        """GET /api/unsubscribe?token=xxx — 一键退订（token 一次性，用后即销毁）。"""
        settings = AlertSettings.from_env(ROOT)
        token = _query_value(query, "token")
        status, subscription = unsubscribe_subscription(
            SubscriptionStore(settings.csv_path), token
        )
        if status == "unsubscribed":
            params = {"notice": "unsubscribed"}
            if subscription:
                params["email"] = subscription.email
                params["campus"] = subscription.campus_name
                params["building"] = subscription.building_name
                params["room"] = subscription.room_name
            self._redirect_to_dashboard(params)
            return
        if status == "already_unsubscribed":
            params = {"notice": "already_unsubscribed"}
            if subscription:
                params["email"] = subscription.email
                params["campus"] = subscription.campus_name
                params["building"] = subscription.building_name
                params["room"] = subscription.room_name
            self._redirect_to_dashboard(params)
            return
        self._redirect_to_dashboard({"notice": "unsubscribe_invalid"})

    def _handle_alert_check(self) -> None:
        if not self._validate_admin_token():
            self._error("UNAUTHORIZED", "Invalid admin token", status=401)
            return
        try:
            data = self._read_request_data()
        except RequestError:
            return
        skip_recent = _truthy(data.get("skipRecent"), default=True)
        stats = AlertRunner(ROOT).run_once(skip_recent=skip_recent)
        self._send_json({"ok": True, "data": stats})

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        base_dir = WEB_DIR.resolve()
        target = (base_dir / path.lstrip("/")).resolve()
        try:
            target.relative_to(base_dir)
        except ValueError:
            self.send_error(404)
            return

        if not target.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _send_plain(self, text: str, status: int = 200) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, status: int = 200) -> None:
        """发送 HTML 页面。"""
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _error(
        self,
        code: str,
        message: str,
        hint: str = "",
        status: int = 400,
    ) -> None:
        """统一错误响应。code 机器可读，message/hint 给人看，向后兼容前端。"""
        self._send_json(
            {
                "ok": False,
                "error": message,
                "hint": hint,
                "error_code": code,
            },
            status=status,
        )

    def _validate_same_origin(self) -> bool:
        host = self.headers.get("Host", "").strip().lower()
        if not host:
            return False
        allowed_origins = {f"http://{host}", f"https://{host}"}
        origin = self.headers.get("Origin", "").strip().lower()
        if origin:
            return origin in allowed_origins
        referer = self.headers.get("Referer", "").strip()
        if referer:
            parsed = urlparse(referer)
            referer_origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
            return referer_origin in allowed_origins
        return True

    def _validate_admin_token(self) -> bool:
        _load_dotenv(str(ENV_FILE))
        expected = os.getenv("ALERT_ADMIN_TOKEN", "").strip()
        supplied = self.headers.get("X-Admin-Token", "").strip()
        return bool(expected and supplied and hmac.compare_digest(supplied, expected))

    def _read_request_data(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._error("INVALID_CONTENT_LENGTH", "Invalid Content-Length", status=400)
            raise RequestError()
        if length > MAX_REQUEST_BODY_BYTES:
            self._error("REQUEST_TOO_LARGE", "Request body too large", status=413)
            raise RequestError()
        body = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")
        if not content_type:
            return {}
        if _content_type_is(content_type, "application/json"):
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error("INVALID_JSON", "Invalid JSON body", status=400)
                raise RequestError()
            if not isinstance(payload, dict):
                self._error("INVALID_JSON", "JSON body must be an object", status=400)
                raise RequestError()
            return {str(key): _clean_request_value(value) for key, value in payload.items()}
        if "multipart/form-data" in content_type:
            headers = f"Content-Type: {content_type}\n\n".encode("utf-8")
            message = BytesParser(policy=policy.default).parsebytes(headers + body)
            return {
                str(part.get_param("name", header="content-disposition")): part.get_payload(
                    decode=True
                ).decode(part.get_content_charset("utf-8")).strip()
                for part in message.iter_parts()
                if part.get_param("name", header="content-disposition")
            }
        if _content_type_is(content_type, "application/x-www-form-urlencoded"):
            try:
                decoded = body.decode("utf-8")
            except UnicodeDecodeError:
                self._error("INVALID_FORM_BODY", "Invalid form body", status=400)
                raise RequestError()
            parsed = parse_qs(decoded, keep_blank_values=True)
            return {key: values[0].strip() if values else "" for key, values in parsed.items()}
        self._error("UNSUPPORTED_MEDIA_TYPE", "Unsupported Content-Type", status=415)
        raise RequestError()

    def _request_base_url(self) -> str:
        _load_dotenv(str(ENV_FILE))
        public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip()
        if _valid_public_base_url(public_base_url):
            return public_base_url.rstrip("/")
        host = self.headers.get("Host", "127.0.0.1:8000").strip() or "127.0.0.1:8000"
        if not _is_allowed_request_host(host):
            host = "127.0.0.1:8000"
        scheme = "https" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else "http"
        return f"{scheme}://{host}"

    def _redirect_to_dashboard(self, params: dict[str, str]) -> None:
        location = f"/?{urlencode(params)}"
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()


def _query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    return values[0].strip() if values else ""


def _is_valid_like_id(value: str) -> bool:
    return bool(LIKE_ID_PATTERN.fullmatch(value))


def _safe_like_id(value: str) -> str:
    return value[:8] + "..." if len(value) > 8 else "***"


def _content_type_is(content_type: str, expected: str) -> bool:
    return content_type.split(";", 1)[0].strip().lower() == expected


def _clean_request_value(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


def _truthy(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _is_allowed_request_host(host: str) -> bool:
    parsed = urlparse(f"//{host}")
    hostname = (parsed.hostname or "").lower()
    return hostname in ALLOWED_HOSTNAMES


def _valid_public_base_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _redact_access_log(message: str) -> str:
    parts = message.split('"')
    for index in range(1, len(parts), 2):
        request_line = parts[index].split()
        if len(request_line) < 2:
            continue
        request_line[1] = _redact_path_query(request_line[1])
        parts[index] = " ".join(request_line)
    return '"'.join(parts)


def _redact_path_query(target: str) -> str:
    parsed = urlparse(target)
    if not parsed.query:
        return target
    query = parse_qs(parsed.query, keep_blank_values=True)
    redacted = {
        key: ["***" if key in SENSITIVE_QUERY_KEYS else value for value in values]
        for key, values in query.items()
    }
    return parsed._replace(query=urlencode(redacted, doseq=True)).geturl()


_likes_lock = threading.Lock()


def _load_likes() -> dict[str, object]:
    if not LIKES_FILE.is_file():
        return {"count": 0, "likedIds": [], "seenIds": [], "totalIssued": 0}
    try:
        data = json.loads(LIKES_FILE.read_text(encoding="utf-8"))
        # 兼容旧格式
        data.setdefault("seenIds", [])
        data.setdefault("totalIssued", 0)
        return data
    except (json.JSONDecodeError, OSError):
        return {"count": 0, "likedIds": [], "seenIds": [], "totalIssued": 0}


def _save_likes(data: dict[str, object]) -> None:
    LIKES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=LIKES_FILE.parent,
            prefix=f".{LIKES_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_name = file.name
            json.dump(data, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        Path(temp_name).replace(LIKES_FILE)
    except Exception:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise


def load_buildings_file() -> list[dict[str, object]]:
    campuses: list[dict[str, object]] = []
    if not BUILDINGS_FILE.is_file():
        return campuses

    campus_pattern = re.compile(r"^##\s+(.+?)\s+client=([^\s]+)")
    building_pattern = re.compile(r"buildingId=\s*(\d+)\s+(.+?)\s*$")
    current: dict[str, object] | None = None
    for line in BUILDINGS_FILE.read_text(encoding="utf-8").splitlines():
        campus_match = campus_pattern.search(line)
        if campus_match:
            current = {
                "client": campus_match.group(2).strip(),
                "name": campus_match.group(1).strip(),
                "buildings": [],
            }
            campuses.append(current)
            continue

        building_match = building_pattern.search(line)
        if building_match and current is not None:
            current["buildings"].append(
                {
                    "id": building_match.group(1),
                    "name": building_match.group(2).strip(),
                }
            )
    return campuses


def default_campuses(config: Config) -> list[dict[str, object]]:
    return [
        {
            "client": config.client,
            "name": config.campus_name,
            "buildings": [{"id": config.building_id, "name": config.building_name}],
        }
    ]


def merge_campuses(*groups: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    campuses_by_client: dict[str, dict[str, object]] = {}

    for group in groups:
        for campus in group:
            client = str(campus.get("client", "")).strip()
            name = str(campus.get("name", "")).strip()
            if not client:
                continue

            target = campuses_by_client.get(client)
            if target is None:
                target = {"client": client, "name": name, "buildings": []}
                campuses_by_client[client] = target
                merged.append(target)

            seen_buildings = {building["id"] for building in target["buildings"]}
            for building in campus.get("buildings", []):
                building_id = str(building.get("id", "")).strip()
                building_name = str(building.get("name", "")).strip()
                if building_id and building_id not in seen_buildings:
                    target["buildings"].append({"id": building_id, "name": building_name})
                    seen_buildings.add(building_id)
    return merged


def _merge_apartment_into_lihu(data: list[dict[str, object]]) -> None:
    """Merge apartment 6 buildings into the 丽湖 campus (client=172.21.101.11)."""
    try:
        buildings_mod = _apartment_mod("buildings")
        apartments = buildings_mod.load_buildings()
        apt_list = [
            {"id": b.code, "name": b.name}
            for b in sorted(apartments.values(), key=lambda x: x.code)
        ]
    except Exception:
        return

    for campus in data:
        if campus.get("client") == "172.21.101.11":
            seen = {b["id"] for b in campus.get("buildings", [])}
            for building in apt_list:
                if building["id"] not in seen:
                    campus["buildings"].append(building)
                    seen.add(building["id"])
            return

    # 如果没有找到丽湖校区，追加
    data.append({
        "client": "172.21.101.11",
        "name": "西丽校区",
        "buildings": apt_list,
    })


def _demo_percentile_for_building(client: str, building_id: str, total_used_kwh: float | None) -> dict:
    """从排行缓存中计算 demo 数据的百分位。"""
    try:
        ranking_data = cached_ranking_for(
            _get_ranking_cache(), client=client, building_id=building_id
        )
        if ranking_data and ranking_data.get("ranking") and total_used_kwh is not None:
            rows = ranking_data["ranking"]
            below = sum(1 for r in rows if r["total_used_kwh"] < total_used_kwh)
            total = len(rows)
            percentile = round(below / total * 100) if total > 0 else 0
            return {
                "building_percentile": percentile,
                "building_rank": below + 1,
                "building_rank_total": total,
            }
    except Exception:
        pass
    return {}


def demo_status() -> dict[str, object]:
    data = {
        "building_id": "7126",
        "client": "192.168.84.87",
        "campus_name": "粤海",
        "building_name": "风槐斋",
        "room_id": "7322",
        "room_name": "713",
        "period": {"begin": "2026-04-20", "end": "2026-05-20", "days": 30},
        "records": 30,
        "threshold_kwh": 20,
        "status": "low",
        "remaining": 18.6,
        "total_used_kwh": 42.8,
        "daily_avg_kwh": 1.43,
        "est_days_left": 13.0,
        "last_record": "2026-05-20",
        "trend": [
            {"date": "2026-05-14", "remaining": 27.8, "daily_used_kwh": 1.5},
            {"date": "2026-05-15", "remaining": 26.1, "daily_used_kwh": 1.7},
            {"date": "2026-05-16", "remaining": 24.9, "daily_used_kwh": 1.2},
            {"date": "2026-05-17", "remaining": 23.0, "daily_used_kwh": 1.9},
            {"date": "2026-05-18", "remaining": 21.4, "daily_used_kwh": 1.6},
            {"date": "2026-05-19", "remaining": 20.0, "daily_used_kwh": 1.4},
            {"date": "2026-05-20", "remaining": 18.6, "daily_used_kwh": 1.4},
        ],
        "recharges": [
            {"time": "2026-05-08", "kwh": 50, "yuan": 30.5, "method": "微信支付"},
            {"time": "2026-04-19", "kwh": 30, "yuan": 18.3, "method": "支付宝"},
        ],
    }
    data.update(_demo_percentile_for_building(data["client"], data["building_id"], data.get("total_used_kwh")))
    return {"ok": True, "data": data}



def _prefetch_github_stars() -> None:
    """后台预抓 GitHub stars，填充内存缓存，避免第一个用户等 5 秒。"""
    global _GITHUB_STARS_CACHE
    url = f"https://api.github.com/repos/{GITHUB_REPO_SLUG}"
    try:
        import httpx as _hx
        resp = _hx.get(url, timeout=5)
        stars = resp.json().get("stargazers_count", 0)
        _GITHUB_STARS_CACHE.update(stars=int(stars), ts=time.time())
        logger.info("GitHub stars pre-fetched: %d", stars)
    except Exception as exc:
        logger.warning("GitHub stars pre-fetch failed: %s", exc)


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="Run the ElectrifySZU dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument(
        "--check-now",
        action="store_true",
        help="Run one alert check immediately before serving.",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Do not skip subscriptions already alerted today.",
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    logger.info("ElectrifySZU dashboard: http://%s:%d", args.host, args.port)
    if args.check_now:
        stats = AlertRunner(ROOT).run_once(skip_recent=not args.no_skip)
        logger.info("startup check finished: %s", stats)
    # 后台预抓 GitHub stars，不阻塞启动
    threading.Thread(
        target=_prefetch_github_stars,
        name="github-stars-prefetch",
        daemon=True,
    ).start()

    alert_thread = start_alert_worker(ROOT, skip_recent=not args.no_skip)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.warning("Shutdown requested (Ctrl+C)...")
    finally:
        logger.info("Shutting down...")

        # Step 1: Signal alert worker to stop
        shutdown_alert_worker()

        # Step 2: Stop accepting new connections and drain in-flight HTTP requests.
        # ThreadingMixIn.block_on_close=True (default) makes server_close() wait
        # for all non-daemon handler threads to finish before returning.
        logger.info("Closing server socket, draining in-flight requests...")
        server.server_close()

        # Step 3: Wait for alert worker thread to finish
        alert_thread.join(timeout=10)
        if alert_thread.is_alive():
            logger.warning("Alert worker thread did not exit within timeout.")

        logger.info("Server stopped.")


if __name__ == "__main__":
    main()
