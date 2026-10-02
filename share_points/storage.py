"""SQLite 持久化层：保存原始事件与每条事件的计分。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .models import ShareEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS share_events (
    event_id    TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    content_id  TEXT NOT NULL,
    platform    TEXT NOT NULL,
    occurred_at TEXT NOT NULL,  -- UTC, ISO 8601
    points      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_share_events_group
    ON share_events (employee_id, content_id, platform);
CREATE INDEX IF NOT EXISTS idx_share_events_scored
    ON share_events (occurred_at) WHERE points > 0;
"""


def _to_utc_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _from_utc_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)


class EventStore:
    """share_events 表的读写封装。"""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def insert_event(self, event: ShareEvent) -> bool:
        """插入事件；同 event_id 已存在则忽略。返回是否为新插入。"""
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO share_events
                (event_id, employee_id, content_id, platform, occurred_at, points)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                event.event_id,
                event.employee_id,
                event.content_id,
                event.platform,
                _to_utc_iso(event.occurred_at),
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def group_events(
        self, employee_id: str, content_id: str, platform: str
    ) -> list[tuple[str, datetime]]:
        """同一员工/内容/平台下的全部事件，按 (发生时间, 事件编号) 升序。"""
        rows = self._conn.execute(
            """
            SELECT event_id, occurred_at FROM share_events
            WHERE employee_id = ? AND content_id = ? AND platform = ?
            ORDER BY occurred_at, event_id
            """,
            (employee_id, content_id, platform),
        ).fetchall()
        return [(event_id, _from_utc_iso(ts)) for event_id, ts in rows]

    def set_points(self, event_id: str, points: int) -> None:
        self._conn.execute(
            "UPDATE share_events SET points = ? WHERE event_id = ?",
            (points, event_id),
        )
        self._conn.commit()

    def leaderboard_rows(
        self, start_utc: datetime | None, end_utc: datetime | None
    ) -> list[tuple[str, int, datetime]]:
        """按员工聚合周期内计分：返回 (员工, 积分, 周期内最后一条计分分享时间)。"""
        where = "points > 0"
        params: list[str] = []
        if start_utc is not None:
            where += " AND occurred_at >= ?"
            params.append(_to_utc_iso(start_utc))
        if end_utc is not None:
            where += " AND occurred_at < ?"
            params.append(_to_utc_iso(end_utc))
        rows = self._conn.execute(
            f"""
            SELECT employee_id, SUM(points) AS total, MAX(occurred_at) AS last_at
            FROM share_events
            WHERE {where}
            GROUP BY employee_id
            """,
            params,
        ).fetchall()
        return [(emp, int(total), _from_utc_iso(last_at)) for emp, total, last_at in rows]

    def employee_points(self, employee_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(points), 0) FROM share_events WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()
        return int(row[0])
