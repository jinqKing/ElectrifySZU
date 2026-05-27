"""Room-to-internal-ID mapping cache.

After the first costly discover_room_id call the result is persisted here so
every later query against the same (source, client, building, room) skips the
three-round-trip campus-scrape entirely.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from electrifyszu.database import get_connection

logger = logging.getLogger("electrifyszu.archive.mapping")

DEFAULT_MAPPING_TTL_DAYS = 30


class MappingRepository:
    """Thread-safe SQLite-backed room-ID mapping cache."""

    def __init__(self, ttl_days: int = DEFAULT_MAPPING_TTL_DAYS) -> None:
        self.ttl_delta = timedelta(days=ttl_days)

    # ── read ──────────────────────────────────────────────────────────

    def get_internal_id(
        self,
        *,
        source: str,
        client: str,
        building_id: str,
        room_name: str,
    ) -> str | None:
        """Return cached internal_id if present and not expired.

        Returns ``None`` when absent or past *expire_after*.
        """
        conn = get_connection()
        row = conn.execute(
            "SELECT internal_id, expire_after FROM room_mappings "
            "WHERE source=? AND client=? AND building_id=? AND room_name=?",
            (source, client, building_id, room_name),
        ).fetchone()

        if row is None:
            return None

        exp = row["expire_after"]
        if exp:
            try:
                if datetime.fromisoformat(exp) < datetime.now():
                    return None
            except ValueError:
                pass
        return str(row["internal_id"]).strip()

    # ── write ─────────────────────────────────────────────────────────

    def put_internal_id(
        self,
        *,
        source: str,
        client: str,
        campus_name: str,
        building_id: str,
        building_name: str,
        room_name: str,
        internal_id: str,
    ) -> None:
        now = datetime.now()
        expire = (now + self.ttl_delta).isoformat()
        conn = get_connection()
        conn.execute(
            "INSERT INTO room_mappings "
            "(source,client,campus_name,building_id,building_name,"
            " room_name,internal_id,discovered_at,refreshed_at,expire_after) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source,client,building_id,room_name) "
            "DO UPDATE SET internal_id=excluded.internal_id, "
            "refreshed_at=CURRENT_TIMESTAMP, "
            "expire_after=excluded.expire_after",
            (source, client, campus_name, building_id, building_name,
             room_name, internal_id,
             now.isoformat(), now.isoformat(), expire),
        )
        conn.commit()
        logger.info(
            "mapped [%s] %s %s -> %s (exp %s)",
            source, building_name, room_name, internal_id, expire,
        )

    # ── bulk helpers ──────────────────────────────────────────────────

    def seeds_needed(self, items: list[dict]) -> list[dict]:
        """Given a list of room-dicts, return subset lacking valid cache."""
        missing: list[dict] = []
        for it in items:
            if self.get_internal_id(
                source=it["source"], client=it["client"],
                building_id=it["building_id"], room_name=it["room_name"],
            ) is None:
                missing.append(it)
        return missing

    def purge_expired(self) -> int:
        conn = get_connection()
        cur = conn.execute(
            "DELETE FROM room_mappings "
            "WHERE expire_after<>'' AND datetime(expire_after)<datetime('now')"
        )
        n = cur.rowcount
        conn.commit()
        if n:
            logger.info("purged %d expired mappings", n)
        return n

    def listing(self, *, source: str, building_id: str | None = None) -> list[dict]:
        """Return all mappings optionally filtered by building."""
        conn = get_connection()
        q = "SELECT * FROM room_mappings WHERE source=?"
        p: tuple = (source,)
        if building_id:
            q += " AND building_id=?"; p = (*p, building_id)
        q += " ORDER BY building_id, room_name"
        return [dict(r) for r in conn.execute(q, p).fetchall()]

    def count(self, *, source: str | None = None) -> int:
        conn = get_connection()
        q = "SELECT COUNT(*) AS c FROM room_mappings"
        p: tuple = ()
        if source:
            q += " WHERE source=?"; p = (source,)
        return conn.execute(q, p).fetchone()["c"]
