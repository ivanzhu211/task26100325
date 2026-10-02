"""验收测试：乱序补传与重复提交不影响最终结果。"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from sharepoints import LeaderboardEntry, Platform, ShareEvent, SharePointsService
from sharepoints.scoring import BEIJING, week_start

UTC = ZoneInfo("UTC")


def build_events() -> list[ShareEvent]:
    """构造一组覆盖各类边界的事件（不含重复提交）。"""
    events: list[ShareEvent] = []
    seq = 0

    def add(emp: str, content: str, platform: Platform, at: datetime) -> None:
        nonlocal seq
        events.append(ShareEvent(f"evt-{seq:04d}", emp, content, platform, at))
        seq += 1

    # 同一员工把同一内容发到同一平台多次（只有最早计分）
    add("emp-a", "post-1", Platform.LINKEDIN, datetime(2026, 9, 29, 10, tzinfo=BEIJING))
    add("emp-a", "post-1", Platform.LINKEDIN, datetime(2026, 9, 28, 9, tzinfo=BEIJING))
    add("emp-a", "post-1", Platform.LINKEDIN, datetime(2026, 9, 30, 8, tzinfo=BEIJING))
    # 发生时间相同，事件编号字典序小的计分
    add("emp-b", "post-2", Platform.TWITTER, datetime(2026, 9, 29, 12, tzinfo=BEIJING))
    add("emp-b", "post-2", Platform.TWITTER, datetime(2026, 9, 29, 12, tzinfo=BEIJING))
    # 跨周边界：北京时间周日 23:59 与周一 00:00 分属两周
    add("emp-c", "post-3", Platform.FACEBOOK, datetime(2026, 10, 4, 23, 59, tzinfo=BEIJING))
    add("emp-c", "post-4", Platform.FACEBOOK, datetime(2026, 10, 5, 0, 0, tzinfo=BEIJING))
    # UTC 时间换算后跨周：UTC 周日 16:30 = 北京周一 00:30
    add("emp-d", "post-5", Platform.LINKEDIN, datetime(2026, 10, 4, 16, 30, tzinfo=UTC))
    # 同一内容发不同平台，各自计分
    add("emp-a", "post-1", Platform.TWITTER, datetime(2026, 9, 29, 11, tzinfo=BEIJING))
    add("emp-a", "post-1", Platform.FACEBOOK, datetime(2026, 9, 29, 11, tzinfo=BEIJING))
    # 不同员工发同一内容互不影响
    add("emp-e", "post-1", Platform.LINKEDIN, datetime(2026, 9, 28, 15, tzinfo=BEIJING))
    # 多周分布
    add("emp-a", "post-6", Platform.TWITTER, datetime(2026, 10, 7, 9, tzinfo=BEIJING))
    add("emp-b", "post-7", Platform.FACEBOOK, datetime(2026, 10, 8, 9, tzinfo=BEIJING))
    # 随机生成更多员工，凑够超过 25 人以验证截断
    rng = random.Random(20261002)
    platforms = list(Platform)
    base = datetime(2026, 9, 28, 0, tzinfo=BEIJING)
    for i in range(40):
        emp = f"emp-x{i:02d}"
        for j in range(rng.randint(1, 6)):
            at = base + timedelta(
                days=rng.randint(0, 13), hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
            )
            add(emp, f"post-r{i}", platforms[rng.randint(0, 2)], at)
    return events


def with_duplicates(events: list[ShareEvent], seed: int) -> list[ShareEvent]:
    """模拟重试：随机把部分事件重复提交多次。"""
    rng = random.Random(seed)
    feed: list[ShareEvent] = []
    for event in events:
        feed.extend([event] * rng.randint(1, 3))
    return feed


def reference(events: list[ShareEvent]) -> dict:
    """独立重算：只由最终事件集合决定结果。"""
    dedup = {e.event_id: e for e in events}
    points_of = {Platform.LINKEDIN: 10, Platform.TWITTER: 8, Platform.FACEBOOK: 5}
    groups: dict[tuple, list[ShareEvent]] = {}
    for e in dedup.values():
        groups.setdefault((e.employee_id, e.content_id, e.platform), []).append(e)
    scored: list[ShareEvent] = []
    score_of: dict[str, int] = {}
    for group in groups.values():
        first = min(group, key=lambda e: (e.occurred_at, e.event_id))
        for e in group:
            score_of[e.event_id] = points_of[e.platform] if e is first else 0
        scored.append(first)

    def board(week: datetime | None) -> list[LeaderboardEntry]:
        totals: dict[str, int] = {}
        last: dict[str, datetime] = {}
        for e in scored:
            if week is not None and week_start(e.occurred_at) != week:
                continue
            totals[e.employee_id] = totals.get(e.employee_id, 0) + score_of[e.event_id]
            last[e.employee_id] = max(last.get(e.employee_id, e.occurred_at), e.occurred_at)
        order = sorted(totals, key=lambda emp: (-totals[emp], last[emp], emp))
        return [
            LeaderboardEntry(i + 1, emp, totals[emp]) for i, emp in enumerate(order[:25])
        ]

    weeks = sorted({week_start(e.occurred_at) for e in dedup.values()})
    employees = sorted({e.employee_id for e in dedup.values()})
    return {
        "total_board": board(None),
        "weekly_boards": {w: board(w) for w in weeks},
        "employee_totals": {
            emp: sum(score_of[e.event_id] for e in dedup.values() if e.employee_id == emp)
            for emp in employees
        },
        "weeks": weeks,
        "employees": employees,
    }


def collect(service: SharePointsService, weeks: list[datetime], employees: list[str]) -> dict:
    return {
        "total_board": service.total_leaderboard(),
        "weekly_boards": {w: service.weekly_leaderboard(w) for w in weeks},
        "employee_totals": {emp: service.employee_total_points(emp) for emp in employees},
    }


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_shuffled_ingest_matches_reference(tmp_path, seed: int) -> None:
    events = build_events()
    ref = reference(events)

    feed = with_duplicates(events, seed)
    random.Random(seed * 1000).shuffle(feed)

    service = SharePointsService(str(tmp_path / f"sp-{seed}.db"))
    try:
        for event in feed:
            service.ingest(event)
        got = collect(service, ref["weeks"], ref["employees"])
    finally:
        service.close()

    assert got["total_board"] == ref["total_board"]
    assert got["weekly_boards"] == ref["weekly_boards"]
    assert got["employee_totals"] == ref["employee_totals"]


def test_different_arrival_orders_give_same_result(tmp_path) -> None:
    events = build_events()
    results = []
    for seed in (11, 22):
        feed = with_duplicates(events, seed)
        random.Random(seed).shuffle(feed)
        service = SharePointsService(str(tmp_path / f"sp-order-{seed}.db"))
        try:
            service.ingest_batch(feed)
            ref = reference(events)
            results.append(collect(service, ref["weeks"], ref["employees"]))
        finally:
            service.close()
    assert results[0] == results[1]


def test_late_earlier_share_moves_points_across_weeks(tmp_path) -> None:
    """晚到的更早分享把计分从另一条记录挪过来，且跨周。"""
    later = ShareEvent(
        "evt-late", "emp-a", "post-1", Platform.LINKEDIN,
        datetime(2026, 10, 5, 9, tzinfo=BEIJING),  # 周一，属于新的一周
    )
    earlier = ShareEvent(
        "evt-early", "emp-a", "post-1", Platform.LINKEDIN,
        datetime(2026, 10, 4, 23, 30, tzinfo=BEIJING),  # 周日，属于上一周
    )
    service = SharePointsService(str(tmp_path / "sp-move.db"))
    try:
        service.ingest(later)
        prev_week = week_start(later.occurred_at) - timedelta(days=7)
        this_week = week_start(later.occurred_at)
        assert service.weekly_leaderboard(this_week)[0].points == 10
        assert service.weekly_leaderboard(prev_week) == []

        service.ingest(earlier)  # 更早的分享晚到，计分挪到上一周
        assert service.weekly_leaderboard(this_week) == []
        assert service.weekly_leaderboard(prev_week)[0].points == 10
        assert service.employee_total_points("emp-a") == 10
        assert service.total_leaderboard() == [
            LeaderboardEntry(rank=1, employee_id="emp-a", points=10)
        ]
    finally:
        service.close()
