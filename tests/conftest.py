from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make room-power-monitor/src importable (needed by server.py module)
_MONITOR_DIR = Path(__file__).resolve().parents[1] / "room-power-monitor"
if str(_MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(_MONITOR_DIR))


@pytest.fixture
def temp_csv_path(tmp_path: Path) -> Path:
    """临时 CSV 路径，隔离测试不影响真实数据。"""
    return tmp_path / "subscriptions.csv"
