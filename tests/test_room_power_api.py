from __future__ import annotations

import pytest

from src.api import ParsedColumnError, _build_trend, _resolve_recharge_columns, _resolve_usage_columns


def test_resolve_usage_columns_by_header_name() -> None:
    row = {
        "\u5269\u4f59\u7535\u91cf": 20.0,
        "\u7d2f\u8ba1\u7528\u7535\u91cf": 30.0,
        "\u6284\u8868\u65f6\u95f4": "2026-05-22",
    }

    columns = _resolve_usage_columns(row)

    assert columns == {
        "remaining": "\u5269\u4f59\u7535\u91cf",
        "total_used": "\u7d2f\u8ba1\u7528\u7535\u91cf",
        "record_time": "\u6284\u8868\u65f6\u95f4",
    }


def test_resolve_recharge_columns_by_header_name() -> None:
    row = {
        "\u652f\u4ed8\u65b9\u5f0f": "\u5fae\u4fe1\u652f\u4ed8",
        "\u5145\u503c\u7535\u91cf": 30,
        "\u5145\u503c\u91d1\u989d": 18.3,
        "\u5145\u503c\u65f6\u95f4": "2026-05-22",
    }

    columns = _resolve_recharge_columns(row)

    assert columns["method"] == "\u652f\u4ed8\u65b9\u5f0f"
    assert columns["kwh"] == "\u5145\u503c\u7535\u91cf"
    assert columns["yuan"] == "\u5145\u503c\u91d1\u989d"
    assert columns["time"] == "\u5145\u503c\u65f6\u95f4"


def test_missing_usage_columns_raise_diagnostic_error() -> None:
    with pytest.raises(ParsedColumnError):
        _resolve_usage_columns({"\u5269\u4f59\u7535\u91cf": 20.0})


def test_build_trend_uses_resolved_columns() -> None:
    records = [
        {
            "\u5269\u4f59\u7535\u91cf": 20.0,
            "\u7d2f\u8ba1\u7528\u7535\u91cf": 10.0,
            "\u6284\u8868\u65f6\u95f4": "2026-05-21",
        },
        {
            "\u5269\u4f59\u7535\u91cf": 18.0,
            "\u7d2f\u8ba1\u7528\u7535\u91cf": 12.5,
            "\u6284\u8868\u65f6\u95f4": "2026-05-22",
        },
    ]

    trend = _build_trend(
        records,
        {
            "remaining": "\u5269\u4f59\u7535\u91cf",
            "total_used": "\u7d2f\u8ba1\u7528\u7535\u91cf",
            "record_time": "\u6284\u8868\u65f6\u95f4",
        },
    )

    assert trend[0]["daily_used_kwh"] == 0.0
    assert trend[1]["daily_used_kwh"] == 2.5
    assert trend[1]["date"] == "2026-05-22"
