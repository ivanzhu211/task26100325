"""计分与排行榜计算：结果只由最终事件集合决定。"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import POINTS_PER_PLATFORM, LeaderboardEntry, ShareEvent

BEIJING = ZoneInfo("Asia/Shanghai")


def week_start(dt: datetime) -> datetime:
    """返回 dt（任意时区）所在周的周一 0 点（北京时间，带时区）。"""
    local = dt.astimezone(BEIJING)
    monday = (local - timedelta(days=local.weekday())).date()
    return datetime(monday.year, monday.month, monday.day, tzinfo=BEIJING)


def score_events(events: list[ShareEvent]) -> dict[str, int]:
    """为每条事件（按事件编号）计算得分。"""
    groups: dict[tuple[str, str, object], list[ShareEvent]] = {}
    for event in events:
        key = (event.employee_id, event.content_id, event.platform)
        groups.setdefault(key, []).append(event)
    scores: dict[str, int] = {}
    for group in groups.values():
        first = min(group, key=lambda e: (e.occurred_at, e.event_id))
        for event in group:
            scores[event.event_id] = (
                POINTS_PER_PLATFORM[event.platform] if event is first else 0
            )
    return scores


def leaderboard(
    events: list[ShareEvent],
    scores: dict[str, int],
    week: datetime | None = None,
    limit: int = 25,
) -> list[LeaderboardEntry]:
    """计算排行榜。week 为 None 表示总榜，否则为该周的周榜。"""
    points: dict[str, int] = {}
    last_scored_at: dict[str, datetime] = {}
    for event in events:
        score = scores[event.event_id]
        if score <= 0:
            continue
        if week is not None and week_start(event.occurred_at) != week:
            continue
        points[event.employee_id] = points.get(event.employee_id, 0) + score
        occurred = event.occurred_at
        if occurred > last_scored_at.get(event.employee_id, datetime.min.replace(tzinfo=BEIJING)):
            last_scored_at[event.employee_id] = occurred
    ordered = sorted(
        points.items(),
        key=lambda kv: (-kv[1], last_scored_at[kv[0]], kv[0]),
    )
    return [
        LeaderboardEntry(rank=index + 1, employee_id=employee_id, points=total)
        for index, (employee_id, total) in enumerate(ordered[:limit])
    ]
