"""对外服务：分享同步服务调用本模块完成记账与排行榜查询。"""
from __future__ import annotations

from datetime import date, datetime

from .models import PLATFORM_POINTS, LeaderboardEntry, ShareEvent
from .storage import EventStore
from .weeks import normalize_week, week_bounds

TOP_N = 25


class SharePointsService:
    """员工分享积分与排行榜服务（库形态，无接口层）。

    结果只由最终收到的事件集合决定：重复事件编号只记一次；
    同员工同内容同平台只给发生最早（时间相同取事件编号字典序最小）的一条计分，
    晚到的更早事件会把计分从其他记录上挪过来。
    """

    def __init__(self, db_path: str) -> None:
        self._store = EventStore(db_path)

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> "SharePointsService":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def ingest(self, event: ShareEvent) -> bool:
        """补传一条事件；返回是否为首次入库（重复事件返回 False）。"""
        if not self._store.insert_event(event):
            return False
        self._rescore_group(event.employee_id, event.content_id, event.platform)
        return True

    def weekly_leaderboard(self, week: date | datetime) -> list[LeaderboardEntry]:
        """指定任意一天所在的自然周（北京时间）的排行榜，前 25 名。"""
        start, end = week_bounds(normalize_week(week))
        return self._leaderboard(start, end)

    def total_leaderboard(self) -> list[LeaderboardEntry]:
        """总榜，前 25 名。"""
        return self._leaderboard(None, None)

    def employee_points(self, employee_id: str) -> int:
        """单个员工的总积分。"""
        return self._store.employee_points(employee_id)

    def _rescore_group(self, employee_id: str, content_id: str, platform: str) -> None:
        """重算同员工/内容/平台一组事件的计分：只有最早一条得分。"""
        group = self._store.group_events(employee_id, content_id, platform)
        points = PLATFORM_POINTS[platform]
        for index, (event_id, _occurred_at) in enumerate(group):
            self._store.set_points(event_id, points if index == 0 else 0)

    def _leaderboard(
        self, start_utc: datetime | None, end_utc: datetime | None
    ) -> list[LeaderboardEntry]:
        rows = self._store.leaderboard_rows(start_utc, end_utc)
        # 积分降序；同分看周期内最后一条计分分享，更早的在前；再按员工编号升序
        rows.sort(key=lambda row: (-row[1], row[2], row[0]))
        return [
            LeaderboardEntry(rank=index + 1, employee_id=emp, points=total, last_scored_at=last_at)
            for index, (emp, total, last_at) in enumerate(rows[:TOP_N])
        ]
