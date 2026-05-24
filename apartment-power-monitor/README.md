# 公寓电费查询模块

> ElectrifySZU 面向 `http://172.25.100.105:8010/` 的宿舍电费查询适配器。

这个目录参考 `room-power-monitor/` 独立放置。旧模块使用 `cgcSims/selectList.do` 下载 Excel；这个站点是 ASP.NET WebForms 页面，需要按页面状态逐步提交楼栋、楼层、房间，再进入购电或用电记录页。

## 工作原理

页面查询流程：

```text
GET /
  -> 读取 drlouming 楼栋下拉框和 __VIEWSTATE
POST /  __EVENTTARGET=drlouming, drlouming=<楼栋编码>
  -> 读取 drceng 楼层下拉框
POST /  __EVENTTARGET=drceng, drlouming=<楼栋编码>, drceng=<楼层编码>
  -> 读取 drfangjian 房间下拉框
POST /  drfangjian=<房间编码>, radio=usedR 或 buyR, ImageButton1.x/y
  -> 进入 usedRecord.aspx 或 buyRecord.aspx，标题区显示剩余电量
POST 记录页 txtstart/txtend/btnser
  -> 得到记录表格；后续分页通过 ?p=2、?p=3 读取
```

已整理的楼栋和房间编码规则见 `data/buildings.txt`。房间编码为：

```text
room_code = <building_code><floor 两位><房间序号两位>
```

例如 `梧桐树#501` 为 `building=01`、`floor=05`、`room=01`，所以 `room_code=010501`。

## 已整理楼栋

| 编码 | 楼栋 | 楼层与房间 |
| --- | --- | --- |
| `01` | 梧桐树# | 5-19 层，每层 31 间 |
| `02` | 青冈栎# | 5-19 层，每层 31 间 |
| `03` | 三角梅# | 4-19 层，每层 31 间 |
| `04` | 冬青树# | 4-19 层，每层 31 间 |
| `05` | 紫罗兰# | 3-19 层，每层 31 间 |
| `06` | B3文韬楼# | 2 层 30 间、3 层 38 间、4 层 22 间 |

## 使用

```powershell
Set-Location apartment-power-monitor
python -m src.cli buildings
python -m src.cli discover 01 501
python -m src.cli usage 01 501 --begin 2026-05-01 --end 2026-05-20
python -m src.cli recharge 01 501 --begin 2026-01-01 --end 2026-05-20
python -m src.cli status 01 501 --days 30
python -m src.cli json 01 501
```

在线读取页面下拉框：

```powershell
python -m src.cli buildings --online
python -m src.cli floors 01
python -m src.cli rooms 01 0105
```

## 配置

可在仓库根目录 `.env` 中覆盖默认配置：

```env
APARTMENT_POWER_BASE=http://172.25.100.105:8010/
APARTMENT_BUILDING_CODE=01
APARTMENT_ROOM_NAME=501
APARTMENT_LOW_POWER_THRESHOLD=20
APARTMENT_POWER_TIMEOUT=15
```

该接口位于校园内网；运行环境需要能访问 `172.25.100.105:8010`。
