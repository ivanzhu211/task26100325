"""员工分享积分与排行榜的自动化测试。

核心验收：一组含重复提交、同内容同平台多次分享、跨周事件的集合，
打乱顺序逐条补传后，所有周榜/总榜/个人积分必须与按最终事件集合
从头算一遍的结果完全一致；换一种到达顺序再跑，结果相同。
"""
from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest

from share_points import LeaderboardEntry, ShareEvent, SharePointsService
from share_points.models import PLATFORM_POINTS
from share_points.weeks import BEIJING, week_bounds, week_start_of

UTC = timezone.utc


# ---------- 参考实现：只根据最终事件集合从头计算 ----------

def reference_scored_events(events: list[ShareEvent]) -> list[tuple[ShareEvent, int]]:
    """按业务规则对最终事件集合从头计分，返回 (事件, 积分) 列表。"""
    by_id = {event.event_id: event for event in events}  # 同事件编号只算一次
    groups: dict[tuple[str, str, str], list[ShareEvent]] = defaultdict(list)
    for event in by_id.values():
        groups[(event.employee_id, event.content_id, event.platform)].append(event)
    scored: list[tuple[ShareEvent, int]] = []
    for (employee_id, content_id, platform), group in groups.items():
        group.sort(key=lambda e: (e.occurred_at, e.event_id))
        for index, event in enumerate(group):
            scored.append((event, PLATFORM_POINTS[platform] if index == 0 else 0))
    return scored


def reference_leaderboard(
    events: list[ShareEvent], week_start=None
) -> list[LeaderboardEntry]:
    scored = reference_scored_events(events)
    totals: dict[str, int] = defaultdict(int)
    last_at: dict[str, datetime] = {}
    for event, points in scored:
        if points <= 0:
            continue
        if week_start is not None:
            lo, hi = week_bounds(week_start)
            if not (lo <= event.occurred_at < hi):
                continue
        totals[event.employee_id] += points
        if event.employee_id not in last_at or event.occurred_at > last_at[event.employee_id]:
            last_at[event.employee_id] = event.occurred_at
    rows = sorted(totals.items(), key=lambda kv: (-kv[1], last_at[kv[0]], kv[0]))
    return [
        LeaderboardEntry(rank=i + 1, employee_id=emp, points=total, last_scored_at=last_at[emp])
        for i, (emp, total) in enumerate(rows[:25])
    ]


def reference_employee_points(events: list[ShareEvent], employee_id: str) -> int:
    return sum(p for e, p in reference_scored_events(events) if e.employee_id == employee_id)


# ---------- 事件集合构造 ----------

def build_event_set() -> list[ShareEvent]:
    """构造一组覆盖各业务规则的事件（含重复提交）。"""
    events: list[ShareEvent] = []
    monday = datetime(2026, 9, 28, 0, 0, tzinfo=BEIJING)  # 北京时间周一 0 点

    # 1) 跨周边界：北京时间周一 0 点前后几秒（用 UTC 表达，验证时区换算）
    boundary = monday.astimezone(UTC)
    events.append(ShareEvent("bd-early", "emp01", "ct1", "linkedin",
                             boundary - timedelta(seconds=5)))   # 上一周
    events.append(ShareEvent("bd-late", "emp01", "ct1", "linkedin",
                             boundary + timedelta(seconds=5)))   # 新的一周，计分被挪走
    events.append(ShareEvent("bd-other", "emp02", "ct1", "linkedin",
                             boundary + timedelta(hours=1)))

    # 2) 同一员工同一内容同一平台多次分享，只有最早计分
    base = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    for i, delta in enumerate([timedelta(hours=5), timedelta(hours=1), timedelta(hours=9)]):
        events.append(ShareEvent(f"multi-{i}", "emp03", "ct2", "twitter", base + delta))

    # 3) 发生时间相同，事件编号字典序小的计分
    same_ts = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
    events.append(ShareEvent("tie-b", "emp04", "ct3", "facebook", same_ts))
    events.append(ShareEvent("tie-a", "emp04", "ct3", "facebook", same_ts))

    # 4) 普通事件：多名员工、多平台、分布在三个自然周
    rng = random.Random(20261002)
    platforms = list(PLATFORM_POINTS)
    for i in range(60):
        emp = f"emp{rng.randint(1, 12):02d}"
        events.append(ShareEvent(
            f"rand-{i:03d}", emp, f"ct{rng.randint(1, 6)}",
            platforms[rng.randrange(len(platforms))],
            monday + timedelta(minutes=rng.randint(0, 60 * 24 * 21)),
        ))

    # 5) 重复提交：随机挑一些事件再传 1~2 遍
    for event in rng.sample(events, 15):
        events.extend([event] * rng.randint(1, 2))
    return events


def ingest_all(service: SharePointsService, events: list[ShareEvent]) -> None:
    for event in events:
        service.ingest(event)


def assert_matches_reference(service: SharePointsService, events: list[ShareEvent]) -> None:
    weeks = {week_start_of(e.occurred_at) for e in events}
    for week in weeks:
        assert service.weekly_leaderboard(week) == reference_leaderboard(events, week), \
            f"周榜不一致: {week}"
    assert service.total_leaderboard() == reference_leaderboard(events)
    for emp in {e.employee_id for e in events}:
        assert service.employee_points(emp) == reference_employee_points(events, emp), emp


# ---------- 验收测试：乱序补传，结果与到达顺序无关 ----------

def test_shuffled_ingestion_matches_reference(tmp_path):
    events = build_event_set()
    for seed in (1, 2):  # 两种不同到达顺序
        shuffled = events[:]
        random.Random(seed).shuffle(shuffled)
        service = SharePointsService(str(tmp_path / f"run{seed}.db"))
        ingest_all(service, shuffled)
        assert_matches_reference(service, events)
        service.close()


def test_interleaved_ingestion_stays_consistent(tmp_path):
    """逐条补传过程中，任意中间时刻的查询也与当时已收事件集合的参考结果一致。"""
    events = build_event_set()
    shuffled = events[:]
    random.Random(7).shuffle(shuffled)
    service = SharePointsService(str(tmp_path / "inc.db"))
    received: list[ShareEvent] = []
    for index, event in enumerate(shuffled):
        service.ingest(event)
        received.append(event)
        if index % 17 == 0:  # 抽样检查中间状态
            assert_matches_reference(service, received)
    assert_matches_reference(service, received)
    service.close()


# ---------- 业务规则单元测试 ----------

def make_service(tmp_path):
    return SharePointsService(str(tmp_path / "test.db"))


def test_duplicate_event_id_counted_once(tmp_path):
    svc = make_service(tmp_path)
    event = ShareEvent("e1", "u1", "c1", "linkedin", datetime(2026, 9, 30, tzinfo=UTC))
    assert svc.ingest(event) is True
    assert svc.ingest(event) is False
    assert svc.ingest(event) is False
    assert svc.employee_points("u1") == 10
    svc.close()


def test_earliest_share_scores_rest_zero(tmp_path):
    svc = make_service(tmp_path)
    svc.ingest(ShareEvent("e2", "u1", "c1", "twitter", datetime(2026, 10, 1, tzinfo=UTC)))
    svc.ingest(ShareEvent("e1", "u1", "c1", "twitter", datetime(2026, 9, 30, tzinfo=UTC)))
    svc.ingest(ShareEvent("e3", "u1", "c1", "twitter", datetime(2026, 10, 2, tzinfo=UTC)))
    assert svc.employee_points("u1") == 8  # 只有最早的 e1 计分
    board = svc.weekly_leaderboard(datetime(2026, 10, 2, tzinfo=UTC))
    assert len(board) == 1
    assert board[0].last_scored_at == datetime(2026, 9, 30, tzinfo=UTC)
    svc.close()


def test_same_timestamp_smaller_event_id_wins(tmp_path):
    svc = make_service(tmp_path)
    ts = datetime(2026, 9, 30, tzinfo=UTC)
    svc.ingest(ShareEvent("z9", "u1", "c1", "facebook", ts))
    svc.ingest(ShareEvent("a1", "u1", "c1", "facebook", ts))
    assert svc.employee_points("u1") == 5
    board = svc.total_leaderboard()
    assert board[0].points == 5  # a1 计分（时间相同，不影响分数，只验证不重复计分）
    svc.close()


def test_beijing_week_boundary(tmp_path):
    svc = make_service(tmp_path)
    # 北京时间 2026-09-28 周一 00:00；前后各一条
    before = ShareEvent("w1", "u1", "c1", "linkedin",
                        datetime(2026, 9, 27, 15, 59, 59, tzinfo=UTC))  # 北京周日 23:59:59
    after = ShareEvent("w2", "u2", "c2", "linkedin",
                       datetime(2026, 9, 27, 16, 0, 0, tzinfo=UTC))   # 北京周一 00:00:00
    svc.ingest(before)
    svc.ingest(after)
    prev_week = svc.weekly_leaderboard(datetime(2026, 9, 22, tzinfo=BEIJING))
    this_week = svc.weekly_leaderboard(datetime(2026, 9, 28, tzinfo=BEIJING))
    assert [e.employee_id for e in prev_week] == ["u1"]
    assert [e.employee_id for e in this_week] == ["u2"]
    svc.close()


def test_late_earlier_event_moves_points_across_weeks(tmp_path):
    svc = make_service(tmp_path)
    later = ShareEvent("b", "u1", "c1", "twitter", datetime(2026, 10, 5, 10, tzinfo=UTC))
    earlier = ShareEvent("a", "u1", "c1", "twitter", datetime(2026, 9, 30, 10, tzinfo=UTC))
    svc.ingest(later)
    week_sep = svc.weekly_leaderboard(datetime(2026, 9, 30, tzinfo=UTC))
    week_oct = svc.weekly_leaderboard(datetime(2026, 10, 5, tzinfo=UTC))
    assert week_sep == [] and len(week_oct) == 1
    svc.ingest(earlier)  # 晚到的更早分享，计分跨周挪移
    week_sep = svc.weekly_leaderboard(datetime(2026, 9, 30, tzinfo=UTC))
    week_oct = svc.weekly_leaderboard(datetime(2026, 10, 5, tzinfo=UTC))
    assert len(week_sep) == 1 and week_sep[0].points == 8
    assert week_oct == []
    assert svc.employee_points("u1") == 8
    svc.close()


def test_leaderboard_tiebreak_last_scored_earlier_first(tmp_path):
    svc = make_service(tmp_path)
    # 两名员工同分；u2 最后一条计分分享更早，应排前面
    svc.ingest(ShareEvent("e1", "u1", "c1", "linkedin", datetime(2026, 9, 29, tzinfo=UTC)))
    svc.ingest(ShareEvent("e2", "u1", "c2", "twitter", datetime(2026, 10, 1, tzinfo=UTC)))
    svc.ingest(ShareEvent("e3", "u2", "c1", "linkedin", datetime(2026, 9, 29, tzinfo=UTC)))
    svc.ingest(ShareEvent("e4", "u2", "c2", "twitter", datetime(2026, 9, 30, tzinfo=UTC)))
    board = svc.total_leaderboard()
    assert [(e.employee_id, e.points) for e in board] == [("u2", 18), ("u1", 18)]
    svc.close()


def test_leaderboard_tiebreak_employee_id(tmp_path):
    svc = make_service(tmp_path)
    ts = datetime(2026, 9, 30, tzinfo=UTC)
    svc.ingest(ShareEvent("e1", "u2", "c1", "facebook", ts))
    svc.ingest(ShareEvent("e2", "u1", "c1", "facebook", ts))
    board = svc.total_leaderboard()
    assert [e.employee_id for e in board] == ["u1", "u2"]  # 同分同时，员工编号升序
    svc.close()


def test_top_25_limit(tmp_path):
    svc = make_service(tmp_path)
    ts = datetime(2026, 9, 30, tzinfo=UTC)
    for i in range(30):
        svc.ingest(ShareEvent(f"e{i:02d}", f"u{i:02d}", "c1", "facebook", ts))
    board = svc.total_leaderboard()
    assert len(board) == 25
    assert board[0].rank == 1 and board[-1].rank == 25
    svc.close()


def test_zero_point_events_excluded_from_leaderboard(tmp_path):
    svc = make_service(tmp_path)
    svc.ingest(ShareEvent("e1", "u1", "c1", "twitter", datetime(2026, 9, 30, tzinfo=UTC)))
    svc.ingest(ShareEvent("e2", "u2", "c1", "twitter", datetime(2026, 10, 1, tzinfo=UTC)))
    svc.ingest(ShareEvent("e3", "u2", "c1", "twitter", datetime(2026, 9, 29, tzinfo=UTC)))
    # u2 的较早分享 e3 到达后，e2 记 0 分；u2 仍有 e3 的 8 分
    svc.ingest(ShareEvent("e4", "u3", "c9", "twitter", datetime(2026, 10, 2, tzinfo=UTC)))
    svc.ingest(ShareEvent("e5", "u3", "c9", "twitter", datetime(2026, 10, 3, tzinfo=UTC)))
    # u3 两条分享同内容同平台，只有一条计分，仍上榜（积分 > 0）
    board = svc.total_leaderboard()
    assert {e.employee_id for e in board} == {"u1", "u2", "u3"}
    svc.close()


def test_unknown_platform_and_naive_datetime_rejected():
    with pytest.raises(ValueError):
        ShareEvent("e1", "u1", "c1", "tiktok", datetime(2026, 9, 30, tzinfo=UTC))
    with pytest.raises(ValueError):
        ShareEvent("e1", "u1", "c1", "twitter", datetime(2026, 9, 30))
