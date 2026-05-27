<p align="center">
  <img src="https://img.shields.io/badge/version-2.7182-2563eb?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/python-3.11+-0f9f6e?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-617083?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/tests-19%20passed-0f9f6e?style=flat-square" alt="tests">
</p>

<h1 align="center">ElectrifySZU</h1>

<p align="center">
  <a href="https://www.iotun.com"><img src="https://img.shields.io/badge/🚀 Live Demo-www.iotun.com-eab308?style=for-the-badge" alt="官网"></a>
</p>

<p align="center">
  <strong style="font-size: 1.3em;">👆 点击上方卡片立即体验在线版 👆</strong>
</p>

<p align="center">
  <strong>深大宿舍电费，不再只有断电时才知道。</strong><br>
  一次查询看到余额、趋势和预警，把校园电费系统变成一个真正的管家。
</p>

***

## 📖 概览

深圳大学宿舍的电费查询系统分散在校园内网网页、企业微信小程序等多个入口。每个入口都需要校园网环境，且查不到余额趋势、没有低电量提醒。

**所有被调研的同学都说同一句话：我们只会在停电时充电费，从来不知道还剩多少。**

ElectrifySZU 把查询、趋势、预警整合到一个页面里：

| 痛点 | 现有系统 | ElectrifySZU |
|------|---------|-------------|
| 查询入口 | 多个系统、多层跳转 | 一个页面，选楼栋+房间号即可 |
| 余额趋势 | 看不到历史 | 30 天折线+柱状图，每日消耗一目了然 |
| 低电量提醒 | 没有 | 邮件自动预警，每天最多一次 |
| 校园网限制 | 必须在校园网 | 支持公网主服务 + 校园内中转节点 |
| GitHub Pages 展示 | 不存在 | `web/` 目录一键部署静态演示 |

## 功能总览

```text
┌─────────────────────────────────────────────────────────┐
│  前端仪表盘 (web/)                                      │
│  ├── 中英双语 SPA (zh-CN / en-US)                       │
│  ├── 宿舍搜索，一键查询余额、用电趋势                    │
│  ├── 指标卡：当前余额 / 日均用电 / 预计可用天数 / 周期用电 │
│  ├── 可交互趋势图：折线+柱状，自定义用电等级              │
│  ├── 充值记录展示 + 预警状态条                           │
│  └── 内置演示数据，无校园网也可完整展示                   │
├─────────────────────────────────────────────────────────┤
│  社区互动模块 (server.py + web/)                         │
│  ├── 免费点赞：每人一次，无需登录                         │
│  ├── 服务端签发 ID，防重复点赞                           │
│  ├── 自动统计使用人数                                    │
│  └── 页脚实时显示点赞数和使用人数                         │
├─────────────────────────────────────────────────────────┤
│  邮件预警订阅 (electrifyszu/subscription/)                │
│  ├── 邮箱验证双确认 (double opt-in)                      │
│  ├── 低电量自动预警（每天最多一次）                       │
│  ├── 每日电费报告（可选）                                 │
│  ├── 一键退订链接                                         │
│  └── 测试模式：绕过校园网直接发送测试预警                  │
├─────────────────────────────────────────────────────────┤
│  数据归档缓存 (electrifyszu/archive/)                      │
│  ├── SQLite 持久化缓存取代纯透传代理                       │
│  ├── 查询优先走缓存（24h内快照），不命中才抓取校园网        │
│  ├── 房间映射、电费快照、日耗数据、充值记录全入库           │
│  ├── 自动定时采集订阅房间                                  │
│  └── CLI：collect / batch / backfill / status / history    │
├─────────────────────────────────────────────────────────┤
│  后端 API 代理 (server.py)                               │
│  ├── /api/status                 宿舍电费查询（cache优先） │
│  ├── /api/buildings              校区楼栋列表             │
│  ├── /api/demo-status            演示数据                 │
│  ├── /api/subscriptions          订阅管理                 │
│  ├── /api/subscriptions/verify   邮箱验证确认             │
│  ├── /api/unsubscribe            一键退订                 │
│  ├── /api/alerts/check           手动触发预警检查         │
│  ├── /api/archive/batch          批量采集过期待归档房间   │
│  ├── /api/archive/status         归档状态概览             │
│  ├── /api/archive/history        房间历史浏览             │
│  ├── /api/version                版本信息                 │
│  ├── /api/health                 健康检查                 │
│  └── /api/stats                  点赞数 + 使用人数        │
├─────────────────────────────────────────────────────────┤
│  CLI 工具 (electrifyszu/)                                 │
│  ├── python -m electrifyszu.dorm.cli status  宿舍电费     │
│  ├── python -m electrifyszu.dorm.discover   发现 roomId   │
│  ├── python -m electrifyszu.archive.cli     归档管理（集、 │
│  │     collect/batch/backfill/status/history）            │
│  ├── python -m electrifyszu.apartment.cli   公寓查询      │
├─────────────────────────────────────────────────────────┤
│  丽湖公寓模块 (electrifyszu/apartment/)                   │
│  适配 http://172.25.100.105:8010/ 的 ASP.NET 公寓电费系统  │
│  ├── python -m electrifyszu.apartment.cli status  公寓电费 │
│  ├── python -m src.cli json        JSON 输出 + 趋势       │
│  ├── python -m src.cli buildings   列出楼栋               │
│  ├── python -m src.cli floors      列出楼层               │
│  └── python -m src.cli rooms       列出房间               │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.11+(3.14)
- [uv](https://docs.astral.sh/uv/) 包管理器

### 本地运行

```bash
git clone https://github.com/jinqKing/ElectrifySZU.git
cd ElectrifySZU

uv sync
cp .env.example .env
# 编辑 .env，填入校园网参数和 SMTP 配置

uv run server.py
```

打开 `http://127.0.0.1:8000`。不在校园网时可点击“载入演示”预览效果。

### CLI 查询

```bash
uv run python -m src.cli status
uv run python -m src.cli json
uv run python -m src.discover <building_id> <room_name>
```

### 丽湖公寓查询

```bash
# 公寓查询示例（丽湖校区）
python -m electrifyszu.apartment.cli buildings              # 列出已知楼栋
python -m electrifyszu.apartment.cli status 01 501          # 查询梧桐树#501 电费状态
python -m electrifyszu.apartment.cli json 01 501            # JSON 格式输出（含30天趋势）
python -m electrifyszu.apartment.cli usage 01 501 --begin 2026-05-01 --end 2026-05-20
python -m electrifyszu.apartment.cli recharge 01 501 --begin 2026-01-01 --end 2026-05-20
```

支持楼栋：梧桐树#、青冈栎#、三角梅#、冬青树#、紫罗兰#、B3文韬楼（丽湖）

### 运行测试

```bash
uv run pytest -v
```

## 环境变量

根目录 `.env` 是统一运行配置入口。真实查询至少需要：

```env
DORM_API_BASE=http://192.168.84.3:9090/cgcSims
DORM_CLIENT=192.168.84.87
DORM_CAMPUS_NAME=深大新斋区
DORM_BUILDING_ID=7126
DORM_BUILDING_NAME=风槐斋
DORM_ROOM_NAME=713
DORM_ROOM_ID=7322
```

邮件订阅、验证、退订和告警任务还需要：

```env
SUBSCRIPTIONS_CSV=data/subscriptions.csv
ALERT_CHECK_TIME=08:00
ALERT_LOOP_INTERVAL=300
PUBLIC_BASE_URL=http://127.0.0.1:8000

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_SSL=true
SMTP_STARTTLS=false
SENDER_EMAIL=warning@example.com
SENDER_PASSWORD=your_email_authorization_code
SENDER_NAME=电费预警系统
```

测试告警链路时可启用：

```env
ALERT_MODE=testing
ALERT_TEST_INTERVAL=300
SKIP_RECENT=1
FORCE_SEND_ALERT=1
FORCE_SEND_DAILY_REPORT=0
```

## 架构

```text
                    ┌──────────────┐
                    │  用户浏览器   │
                    └──────┬───────┘
                           │ HTTP
                    ┌──────▼───────┐
                    │  server.py   │
                    │  API 代理    │
                    └──┬───┬───┬──┘
                       │   │   │
          ┌────────────┘   │   └────────────┐
          ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────┐
│ electrifyszu │ │ electrifyszu │ │ web/             │
│ dorm/        │ │ /subscription│ │ 静态文件服务     │
│ apartment/   │ │ /            │ │                  │
│              │ │ 邮箱验证      │ │ index.html       │
│ DormApi      │ │ 预警线程      │ │ app.js           │
│ AptPowerApi  │ │ SMTP 发送     │ │ work-intro.html  │
└──────┬───────┘ └──────┬───────┘ └──────────────────┘
       │               │
       └───────┬───────┘
               ▼
┌──────────────────────────┐
│ electrifyszu/archive/    │
│ Power Archive (SQLite)   │
│ ├─ mapping_repo          │
│ ├─ snapshot_storage      │
│ ├─ collector             │
│ └─ tasks                 │
│                          │
│ Cache HIT → zero-latency │
│ Cache MISS → poll campus │
└──────┬───────────────────┘
       │
       ▼
┌─────────────────┐
│ 校园内网电费系统 │
└─────────────────┘
```

公网部署时推荐把“公网访问”和“校园内网访问”拆开：

```text
公网用户 -> Nginx -> ElectrifySZU 容器 -> 校园内中转链路 -> 电费系统
```

后端只需要能访问 `DORM_API_BASE` 指向的地址即可。这个地址可以是校园内网原始接口，也可以是校内机器反向映射到公网服务器宿主机的本地端口。

## 部署

完整部署指南（含 SQLite 迁移、Docker、Nginx、SSH 隧道、运维备份）请移步 **[DEPLOY.md](DEPLOY.md)**。

### 快速参考

| 场景 | 命令 / 文档 |
|:-----|:------------|
| 本地开发 | `uv run server.py --port 8000` |
| 公网服务器 | `docker compose -f compose.public.yml up -d` |
| 校园网机器 | `docker compose -f compose.campus.yml up -d` |
| SQLite 迁移 | `uv run python scripts/migrate_to_sqlite.py` |
| 隧道搭建 | 参看 [DEPLOY.md#6-ssh-隧道搭建](DEPLOY.md#6-ssh-隧道搭建) |
| GitHub Pages | `.github/workflows/pages.yml` 自动部署 `web/` |

## 项目结构

```text
.
├── electrifyszu/               # 后端核心包
│   ├── archive/               # 电力数据归档缓存（SQLite持久化）
│   ├── dorm/                  # 粤海校区宿舍电费查询
│   ├── apartment/             # 丽湖校区公寓电费查询
│   ├── ranking/               # 楼栋排行
│   ├── subscription/          # 邮件订阅预警
│   ├── server/                # HTTP 服务器
│   ├── data/                  # 数据文件
│   │   ├── buildings.txt      # 校区楼栋列表
│   │   └── apartment_buildings.txt # 公寓楼栋列表
│   ├── database.py            # SQLite 数据库（含归档表）
│   └── config.py              # 统一配置
├── web/                       # 前端静态资源
│   ├── index.html             # 主仪表盘
│   ├── app.js                 # 前端逻辑
│   ├── styles.css             # 样式
│   ├── i18n-data.js           # 中英文文案
│   └── work-intro.html        # 团队介绍幻灯片
├── tests/                     # 测试
├── deploy/nginx/              # Nginx 示例配置
├── compose.yml                # Docker Compose 部署文件
├── Dockerfile                 # 生产镜像定义
├── server.py                  # HTTP 服务 & API 代理
├── log_config.py              # 结构化日志配置
├── SUBSCRIPTION_FLOW.md       # 订阅流程文档
├── pyproject.toml             # 项目配置
└── .env.example               # 环境变量模板
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 查询宿舍电费余额与用电记录 |
| GET | `/api/buildings` | 获取校区与楼栋列表 |
| GET | `/api/demo-status` | 获取演示数据（无需校园网） |
| POST | `/api/subscriptions` | 创建电费预警订阅 |
| GET | `/api/subscriptions/verify` | 邮箱验证确认 |
| GET | `/api/unsubscribe` | 取消订阅 |
| POST | `/api/alerts/check` | 手动触发预警检查（需 `X-Admin-Token`） |
| POST | `/api/archive/batch` | 批量采集过期待归档房间（需 `X-Admin-Token`） |
| GET | `/api/archive/status` | 归档表行数统计与最近运行记录（需 `X-Admin-Token`） |
| GET | `/api/archive/history` | 房间历史趋势与充值记录查询（需 `X-Admin-Token`） |
| GET | `/api/version` | 服务版本信息 |
| GET | `/api/health` | 健康检查 |
| POST | `/api/like/init` | 签发点赞者 ID（首次访问自动调用） |
| POST | `/api/like` | 点赞（每人一次，仅接受已签发 ID） |
| GET | `/api/like/count` | 获取点赞总数 |
| GET | `/api/like/my` | 检查当前 ID 是否已点赞 |
| GET | `/api/stats` | 综合统计 |

所有响应统一格式：

```json
{"ok": true, "data": {}}
```

```json
{"ok": false, "error": "人类可读消息", "hint": "建议操作", "error_code": "ROOM_NOT_FOUND"}
```

错误码包括：`ROOM_NOT_FOUND`、`CAMPUS_NETWORK_ERROR`、`INVALID_EMAIL`、`MISSING_FIELD`、`INVALID_THRESHOLD`、`EMAIL_DELIVERY_FAILED`、`INTERNAL_ERROR`、`NOT_FOUND`、`INVALID_LIKE_ID`。

运维说明：

- `POST /api/alerts/check` 需要请求头 `X-Admin-Token`，其值必须匹配环境变量 `ALERT_ADMIN_TOKEN`。
- `PUBLIC_BASE_URL` 会优先用于生成验证/退订邮件链接；未配置时服务端只会回退到安全的本地地址。

## Matrix 团队

ElectrifySZU 由 Matrix 团队开发维护。我们也是深大学生，也在用这个工具查电费。

- [飞书项目 Wiki](https://my.feishu.cn/wiki/EuOXwd1Efi0uLCktmx7cIocynBb)
- [工作介绍幻灯片](web/work-intro.html)
- 觉得有用的话，欢迎给项目一个 Star

## 已知限制

- `roomId` 与 `roomName` 必须匹配，输入错误会导致查询失败。
- 如果宿主机无法访问 `DORM_API_BASE`，真实查询与自动告警都不会工作。
- GitHub Pages 只能托管静态前端，不能替代后端 API。
- 当前公开 API 只有基础限流，长期公网运行仍建议继续补充验证码、邮箱确认、审计日志和备份。

## 许可证

MIT License © Matrix Team
