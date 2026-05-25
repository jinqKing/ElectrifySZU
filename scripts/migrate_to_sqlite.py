#!/usr/bin/env python
"""Migrate legacy CSV/JSON data to SQLite.

Usage:
    python scripts/migrate_to_sqlite.py

This script reads from:
    data/likes.json          → likes table
    data/subscriptions.csv   → subscriptions table

And writes to:
    data/electrifyszu.db     (created if not exists)

Safe to run multiple times — uses INSERT OR IGNORE.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from electrifyszu.database import (
    init_db,
    get_db_path,
    migrate_from_legacy,
    LIKES_LEGACY_FILE,
    SUBS_LEGACY_FILE,
)


def main() -> int:
    db_path = get_db_path()

    print(f"ElectrifySZU — SQLite Migration")
    print(f"{'=' * 40}")
    print(f"Database: {db_path}")

    if db_path.is_file():
        size = db_path.stat().st_size
        print(f"  Existing DB: {size:,} bytes")
    else:
        print(f"  DB does not exist yet — will create")

    # Check for legacy files
    has_likes = LIKES_LEGACY_FILE.is_file()
    has_subs = SUBS_LEGACY_FILE.is_file()

    if not has_likes and not has_subs:
        print(f"\nNo legacy data found.")
        print(f"  Looking for: {LIKES_LEGACY_FILE}")
        print(f"  Looking for: {SUBS_LEGACY_FILE}")
        print(f"\nNothing to migrate. Database initialized empty.")
        init_db()
        return 0

    print(f"\nLegacy files found:")
    if has_likes:
        likes_size = LIKES_LEGACY_FILE.stat().st_size
        print(f"  ✅ likes.json        ({likes_size:,} bytes)")
    else:
        print(f"  ❌ likes.json        (not found)")
    if has_subs:
        subs_size = SUBS_LEGACY_FILE.stat().st_size
        print(f"  ✅ subscriptions.csv ({subs_size:,} bytes)")
    else:
        print(f"  ❌ subscriptions.csv (not found)")

    print(f"\nMigrating...")
    stats = migrate_from_legacy()

    print(f"\nMigration complete:")
    print(f"  Subscriptions imported: {stats['subscriptions']}")
    print(f"  Likes imported:         {stats['likes']}")
    print(f"  Errors:                 {stats['errors']}")

    if stats["errors"]:
        print(f"\n⚠️  Some errors occurred during migration.")
        print(f"   Check the logs above for details.")
        return 1

    print(f"\n✅ Migration successful!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
