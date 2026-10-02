"""SQLite 事件存储：负责持久化与事件编号去重。"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .models import Platform, ShareEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS share_events (
    event_id    TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL,
    content_id  TEXT NOT NULL,
    platform    TEXT NOT NULL,
    occurred_at TEXT NOT NULL
)
"""


class EventStore:
    """把分享事件存入本地 SQLite 文件，同一事件编号只保留一条。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def add(self, event: ShareEvent) -> bool:
        """写入事件；已存在相同事件编号则忽略。返回是否真正写入。"""
        if event.occurred_at.tzinfo is None:
            raise ValueError("occurred_at 必须带时区")
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO share_events"
            " (event_id, employee_id, content_id, platform, occurred_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.employee_id,
                event.content_id,
                event.platform.value,
                event.occurred_at.isoformat(),
            ),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def all_events(self) -> list[ShareEvent]:
        """读出全部已去重的事件。"""
        rows = self._conn.execute(
            "SELECT event_id, employee_id, content_id, platform, occurred_at"
            " FROM share_events"
        ).fetchall()
        return [
            ShareEvent(
                event_id=row[0],
                employee_id=row[1],
                content_id=row[2],
                platform=Platform(row[3]),
                occurred_at=datetime.fromisoformat(row[4]),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()
