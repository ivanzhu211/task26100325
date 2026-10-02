"""计分与名次规则的单元测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sharepoints import Platform, ShareEvent, SharePointsService
from sharepoints.scoring import BEIJING, week_start


def make_service(tmp_path):
    return SharePointsService(str(tmp_path / "sp.db"))


def test_week_start_uses_beijing_time() -> None:
    # 北京时间周一 00:00 整点属于新的一周
    assert week_start(datetime(2026, 10, 5, 0, 0, tzinfo=BEIJING)) == datetime(
        2026, 10, 5, tzinfo=BEIJING
    )
    # 北京时间周日 23:59 仍属于上一周
    assert week_start(datetime(2026, 10, 4, 23, 59, tzinfo=BEIJING)) == datetime(
        2026, 9, 28, tzinfo=BEIJING
    )
    # 其他时区换算：UTC 周日 16:00 = 北京周一 00:00
    assert week_start(datetime(2026, 10, 4, 16, 0, tzinfo=timezone.utc)) == datetime(
        2026, 10, 5, tzinfo=BEIJING
    )


def test_same_instant_scored_by_event_id_order(tmp_path) -> None:
    service = make_service(tmp_path)
    try:
        at = datetime(2026, 10, 6, 10, tzinfo=BEIJING)
        service.ingest(ShareEvent("evt-z", "emp-a", "c1", Platform.TWITTER, at))
        service.ingest(ShareEvent("evt-a", "emp-a", "c1", Platform.TWITTER, at))
        # 字典序小的 evt-a 计分，但总分不变；两条都保存
        assert service.employee_total_points("emp-a") == 8
        assert len(service._store.all_events()) == 2
    finally:
        service.close()


def test_tie_break_by_last_scored_share_then_employee_id(tmp_path) -> None:
    service = make_service(tmp_path)
    try:
        # emp-a 与 emp-b 同分；emp-a 最后一条计分分享更早，排前面
        service.ingest(ShareEvent(
            "e1", "emp-a", "c1", Platform.LINKEDIN,
            datetime(2026, 10, 6, 8, tzinfo=BEIJING),
        ))
        service.ingest(ShareEvent(
            "e2", "emp-b", "c1", Platform.LINKEDIN,
            datetime(2026, 10, 6, 9, tzinfo=BEIJING),
        ))
        # emp-c 与 emp-d 同分且最后计分分享同时刻，按员工编号升序
        service.ingest(ShareEvent(
            "e3", "emp-d", "c2", Platform.LINKEDIN,
            datetime(2026, 10, 6, 10, tzinfo=BEIJING),
        ))
        service.ingest(ShareEvent(
            "e4", "emp-c", "c3", Platform.LINKEDIN,
            datetime(2026, 10, 6, 10, tzinfo=BEIJING),
        ))
        board = service.total_leaderboard()
        assert [e.employee_id for e in board] == ["emp-a", "emp-b", "emp-c", "emp-d"]
        assert [e.rank for e in board] == [1, 2, 3, 4]
    finally:
        service.close()


def test_leaderboard_limit_25(tmp_path) -> None:
    service = make_service(tmp_path)
    try:
        for i in range(30):
            service.ingest(ShareEvent(
                f"e{i:02d}", f"emp-{i:02d}", "c1", Platform.FACEBOOK,
                datetime(2026, 10, 6, 10, tzinfo=BEIJING) + timedelta(minutes=i),
            ))
        board = service.total_leaderboard()
        assert len(board) == 25
        assert board[0].rank == 1 and board[-1].rank == 25
    finally:
        service.close()


def test_duplicate_event_id_ingested_once(tmp_path) -> None:
    service = make_service(tmp_path)
    try:
        event = ShareEvent(
            "e1", "emp-a", "c1", Platform.LINKEDIN,
            datetime(2026, 10, 6, 10, tzinfo=BEIJING),
        )
        assert service.ingest(event) is True
        assert service.ingest(event) is False
        assert service.ingest_batch([event, event]) == 0
        assert service.employee_total_points("emp-a") == 10
    finally:
        service.close()


def test_naive_datetime_rejected(tmp_path) -> None:
    service = make_service(tmp_path)
    try:
        event = ShareEvent("e1", "emp-a", "c1", Platform.LINKEDIN, datetime(2026, 10, 6, 10))
        try:
            service.ingest(event)
            raise AssertionError("应当拒绝不带时区的 occurred_at")
        except ValueError:
            pass
    finally:
        service.close()
