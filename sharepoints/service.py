"""对外门面：供上层分享同步服务调用。"""
from __future__ import annotations

from datetime import datetime

from .models import LeaderboardEntry, ShareEvent
from .scoring import leaderboard, score_events, week_start
from .store import EventStore


class SharePointsService:
    """员工分享积分与排行榜服务。"""

    def __init__(self, db_path: str) -> None:
        self._store = EventStore(db_path)

    def ingest(self, event: ShareEvent) -> bool:
        """补传一条分享事件；重复事件编号自动忽略。返回是否新写入。"""
        return self._store.add(event)

    def ingest_batch(self, events: list[ShareEvent]) -> int:
        """批量补传，返回实际新写入的条数。"""
        return sum(1 for event in events if self._store.add(event))

    def weekly_leaderboard(self, any_time_in_week: datetime) -> list[LeaderboardEntry]:
        """指定时刻所在周（北京时间周）的周榜，前 25 名。"""
        events = self._store.all_events()
        return leaderboard(events, score_events(events), week=week_start(any_time_in_week))

    def total_leaderboard(self) -> list[LeaderboardEntry]:
        """总榜，前 25 名。"""
        events = self._store.all_events()
        return leaderboard(events, score_events(events))

    def employee_total_points(self, employee_id: str) -> int:
        """单个员工的总积分。"""
        events = self._store.all_events()
        scores = score_events(events)
        return sum(
            scores[event.event_id]
            for event in events
            if event.employee_id == employee_id
        )

    def close(self) -> None:
        self._store.close()
