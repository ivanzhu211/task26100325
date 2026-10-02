"""北京时间（UTC+8）周边界工具。一周 = 周一 00:00 到下周一 00:00。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BEIJING = ZoneInfo("Asia/Shanghai")


def week_start_of(moment: datetime) -> date:
    """返回某个带时区时刻所在周（北京时间）的周一日期。"""
    local = moment.astimezone(BEIJING)
    return local.date() - timedelta(days=local.weekday())


def normalize_week(day: date | datetime) -> date:
    """把任意日期/时刻归一到它所在周的周一（北京时间）。"""
    if isinstance(day, datetime):
        return week_start_of(day)
    if isinstance(day, date):
        return day - timedelta(days=day.weekday())
    raise TypeError(f"不支持的类型: {type(day)!r}")


def week_bounds(week_start: date) -> tuple[datetime, datetime]:
    """返回 [周一开始, 下周一开始) 两个带时区时刻。"""
    start = datetime(week_start.year, week_start.month, week_start.day, tzinfo=BEIJING)
    return start, start + timedelta(days=7)
