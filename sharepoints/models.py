"""数据类型定义。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Platform(str, Enum):
    LINKEDIN = "linkedin"
    TWITTER = "twitter"
    FACEBOOK = "facebook"


POINTS_PER_PLATFORM: dict[Platform, int] = {
    Platform.LINKEDIN: 10,
    Platform.TWITTER: 8,
    Platform.FACEBOOK: 5,
}


@dataclass(frozen=True)
class ShareEvent:
    """员工分享事件（由离线客户端生成，联网后补传）。"""

    event_id: str
    employee_id: str
    content_id: str
    platform: Platform
    occurred_at: datetime  # 必须带时区


@dataclass(frozen=True)
class LeaderboardEntry:
    """排行榜条目。"""

    rank: int
    employee_id: str
    points: int
