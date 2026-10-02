# sharepoints：员工分享积分与排行榜库

供上层分享同步服务调用的 Python 库，数据持久化在本地 SQLite 文件，无接口层、无外部服务依赖。

## 用法

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from sharepoints import Platform, ShareEvent, SharePointsService

service = SharePointsService("sharepoints.db")

# 补传分享事件（occurred_at 必须带时区；重复 event_id 自动忽略）
service.ingest(ShareEvent(
    event_id="evt-001",
    employee_id="emp-01",
    content_id="post-1",
    platform=Platform.LINKEDIN,
    occurred_at=datetime(2026, 9, 28, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
))

service.weekly_leaderboard(datetime.now(ZoneInfo("Asia/Shanghai")))  # 该时刻所在周的周榜（前 25）
service.total_leaderboard()          # 总榜（前 25）
service.employee_total_points("emp-01")  # 单个员工总积分
service.close()
```

## 规则

- 计分：LinkedIn 10 分、Twitter 8 分、Facebook 5 分。
- 同一员工 + 同一内容 + 同一平台只给发生时间最早的一次计分（同时刻取事件编号字典序最小者），其余保存但记 0 分。
- 一周为北京时间周一 00:00 至下周一 00:00，计分计入分享发生时间所在周。
- 周榜/总榜取积分大于 0 的前 25 名；同分时该周期内最后一条计分分享更早者在前，再相同按员工编号升序。
- 结果只由最终收到的事件集合决定：事件按 event_id 去重后存储，查询时基于全集重算，与到达顺序、重复次数无关；晚到的更早分享会自动把计分（含跨周）挪到正确的记录上。

## 测试

```bash
python3 -m pytest tests/ -q
```
