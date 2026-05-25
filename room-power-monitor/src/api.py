"""Backward-compatible re-exports from electrifyszu.dorm.api.

Kept for existing code. New code: `from electrifyszu.dorm.api import DormApi`.
"""
from electrifyszu.dorm.api import (  # noqa: F401
    DormApi,
    ParsedColumnError,
    parse_excel,
    _build_trend,
    _resolve_recharge_columns,
    _resolve_usage_columns,
    _to_float,
    _status_level,
)
