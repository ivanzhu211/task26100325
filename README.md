# share-points

员工分享积分与排行榜模块，以库的形式提供给上层分享同步服务调用，无接口层。
数据持久化在本地 SQLite 文件中。

## 业务规则

- 分享事件带客户端生成的事件编号、员工编号、内容编号、平台和发生时间（带时区）；
  同一事件编号重复提交只算一次。
- 计分：LinkedIn 10 分、Twitter 8 分、Facebook 5 分。同一员工把同一内容分享到
  同一平台多次，只有发生时间最早的那次计分（时间相同取事件编号字典序最小者），
  其余照常保存但记 0 分。
- 一周指北京时间周一 00:00 到下周一 00:00，计分算进分享发生时间所在的周。
- 周榜（任意一周，含过去的周）和总榜各返回积分大于 0 的前 25 名；积分相同的，
  周期内最后一条计分分享发生得更早的排前面；再相同按员工编号升序。
- 结果只由最终收到的事件集合决定，与到达顺序、重复次数无关；晚到的更早分享
  会把计分从其他记录上挪过来（可能跨周），榜单与名次随之更新。

## 用法

```python
from datetime import datetime, timezone
from share_points import ShareEvent, SharePointsService

service = SharePointsService("share_points.db")  # 本地 SQLite 文件

service.ingest(ShareEvent(
    event_id="01J...",
    employee_id="E1001",
    content_id="C2001",
    platform="linkedin",          # linkedin / twitter / facebook
    occurred_at=datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc),
))

service.weekly_leaderboard(datetime(2026, 9, 30, tzinfo=timezone.utc))  # 该日所在周（北京时间）前 25 名
service.total_leaderboard()      # 总榜前 25 名
service.employee_points("E1001") # 单个员工总积分
service.close()
```

## 测试

```bash
python3 -m pytest tests/ -q
```
