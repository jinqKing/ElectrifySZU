"""
ElectrifySZU — 结构化日志配置

用法（在 server.py/main 入口调用一次）:
    from log_config import setup_logging
    setup_logging()

然后在各模块中使用标准 logging.getLogger(__name__):
    import logging
    logger = logging.getLogger(__name__)
    logger.info("...")
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


# ── ANSI 颜色 ──────────────────────────────────────────────────────────────
class _Colors:
    """终端 ANSI 转义码（Windows 10+ 原生支持）。"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # 前景色
    GREY = "\033[38;5;244m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD_RED = "\033[1;31m"

    # 级别 → 颜色映射
    LEVEL_MAP = {
        logging.DEBUG: DIM,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    @classmethod
    def level_color(cls, level: int) -> str:
        return cls.LEVEL_MAP.get(level, cls.RESET)

# ── 日志格式 ──────────────────────────────────────────────────────────────
# 示例行:
#   2026-05-22 12:00:00 | INFO    | server      | 127.0.0.1 - GET /api/status → 200 (45ms)
#   2026-05-22 12:00:00 | WARNING | email       | retry to=user@example.com attempt=1 wait=2.5s

LOG_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── 默认值 ────────────────────────────────────────────────────────────────
DEFAULT_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_BACKUP_COUNT = 5


def _resolve_project_root() -> Path:
    """向上查找项目根目录（包含 pyproject.toml 或 .env 的目录）。"""
    here = Path(__file__).resolve().parent
    for candidate in (here, here.parent):
        if (candidate / "pyproject.toml").is_file() or (
            candidate / ".env"
        ).is_file():
            return candidate
    return here


class ColoredFormatter(logging.Formatter):
    """终端带颜色的 Formatter（文件 Handler 用普通 Formatter）。"""

    def __init__(self) -> None:
        super().__init__(LOG_FORMAT, DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        # 时间戳
        asctime = self.formatTime(record, self.datefmt)
        # 级别（按等级着色）
        level_color = _Colors.level_color(record.levelno)
        colored_level = f"{level_color}{record.levelname:<7}{_Colors.RESET}"
        # 模块名（青色）
        colored_name = f"{_Colors.CYAN}{record.name:<12}{_Colors.RESET}"
        # 消息
        msg = record.getMessage()
        return f"{asctime} | {colored_level} | {colored_name} | {msg}"


def setup_logging(
    *,
    level: str | None = None,
    log_dir: str | Path | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> None:
    """一次性初始化日志系统。

    参数可从环境变量覆盖:
        LOG_LEVEL       — 日志级别 (DEBUG/INFO/WARNING/ERROR, 默认 INFO)
        LOG_DIR         — 日志目录 (默认 logs/)
        LOG_MAX_BYTES   — 单个日志文件大小 (默认 10MB)
        LOG_BACKUP_COUNT — 保留备份数 (默认 5)

    调用多次是安全的（重复调用会被 root logger 忽略）。
    """
    # ── 解析配置 ──
    resolved_level = (
        level
        or os.getenv("LOG_LEVEL", "")
        or DEFAULT_LEVEL
    ).strip().upper()

    log_dir_path = Path(
        log_dir or os.getenv("LOG_DIR", "") or DEFAULT_LOG_DIR
    )
    if not log_dir_path.is_absolute():
        log_dir_path = _resolve_project_root() / log_dir_path

    resolved_max_bytes = (
        max_bytes
        or _int_env("LOG_MAX_BYTES", DEFAULT_MAX_BYTES)
    )
    resolved_backup_count = (
        backup_count
        or _int_env("LOG_BACKUP_COUNT", DEFAULT_BACKUP_COUNT)
    )

    # ── Root logger ──
    root = logging.getLogger()
    # 防止重复调用时重复添加 handler
    if root.handlers:
        return

    root.setLevel(logging.DEBUG)  # handler 各自控制实际输出级别

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # ── 控制台 Handler（彩色） ──
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(_parse_level(resolved_level))
    console.setFormatter(ColoredFormatter())
    root.addHandler(console)

    # ── 滚动文件 Handler ──
    log_dir_path.mkdir(parents=True, exist_ok=True)
    log_file = log_dir_path / "electrifyszu.log"
    file_handler = RotatingFileHandler(
        str(log_file),
        maxBytes=resolved_max_bytes,
        backupCount=resolved_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # ── 启动标记 ──
    logging.getLogger(__name__).info(
        "Logging initialized: level=%s, file=%s (max=%d, backup=%d)",
        resolved_level,
        log_file,
        resolved_max_bytes,
        resolved_backup_count,
    )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _parse_level(name: str) -> int:
    return getattr(logging, name, logging.INFO)


# ── 快捷创建子模块 logger ─────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    """等价于 logging.getLogger(name)，语义更清晰。"""
    return logging.getLogger(name)
