from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def temp_csv_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Temporary path for isolated test data.

    Sets ELECTRIFYSZU_DB_PATH so the SQLite DB lives in the temp dir.
    The returned path mimics the legacy CSV path for backward compat.
    """
    db_path = tmp_path / "electrifyszu.db"
    monkeypatch.setenv("ELECTRIFYSZU_DB_PATH", str(db_path))
    return tmp_path / "subscriptions.csv"
