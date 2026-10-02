"""数据模型与计分常量。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

PLATFORM_POINTS: dict[str, int] = {
    "linkedin": 10,
    "twitter": 8,
    "facebook": 5,
}


@dataclass(frozen=True)
class ShareEvent:
    """一条员工分享事件（由离线客户端生成，可能重复、乱序到达）。"""

    event_id: str
    employee_id: str
    content_id: str
    platform: str
    occurred_at: datetime  # 必须带时区

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id 不能为空")
        if not self.employee_id:
            raise ValueError("employee_id 不能为空")
        if not self.content_id:
            raise ValueError("content_id 不能为空")
        platform = self.platform.lower()
        if platform not in PLATFORM_POINTS:
            raise ValueError(f"不支持的平台: {self.platform!r}")
        object.__setattr__(self, "platform", platform)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at 必须带时区")


@dataclass(frozen=True)
class LeaderboardEntry:
    """排行榜条目。"""

    rank: int
    employee_id: str
    points: int
    last_scored_at: datetime  # 周期内最后一条计分分享的发生时间
