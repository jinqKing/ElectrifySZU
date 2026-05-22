<p align="center">
  <img src="https://img.shields.io/badge/version-2.71-2563eb?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/python-3.11+-0f9f6e?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-617083?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/tests-19%20passed-0f9f6e?style=flat-square" alt="tests">
</p>

<h1 align="center">⚡ ElectrifySZU</h1>

<p align="center">
  <strong>深大宿舍电费，不再只有断电时才知道。</strong><br>
  一次查询看到余额、趋势和预警 —— 把校园电费系统变成一个真正的管家。
</p>

---

## 这个项目解决什么问题

深圳大学宿舍的电费查询系统分散在校园内网网页、企业微信小程序等多个入口。每个入口都需要校园网环境，且查不到余额趋势、没有低电量提醒。

**所有被调研的同学都说同一句话：我们只会在停电时充电费，从来不知道还剩多少。**

ElectrifySZU 把查询、趋势、预警整合到一个页面里：

| 痛点 | 现有系统 | ElectrifySZU |
|------|---------|-------------|
| 查询入口 | 多个系统、多层跳转 | 一个页面，选楼栋+房间号即可 |
| 余额趋势 | 看不到历史 | 30 天折线+柱状图，每日消耗一目了然 |
| 低电量提醒 | **没有** | 邮件自动预警，每天最多一次 |
| 校园网限制 | 必须在校园网 | 内置演示数据，离线也能看效果 |
| GitHub Pages 展示 | 不存在 | `web/` 目录一键部署静态演示 |

## 功能总览

```
┌─────────────────────────────────────────────────────────┐
│  🌐 前端仪表盘 (web/)                                    │
│  ├── 中英双语 SPA (zh-CN / en-US)                        │
│  ├── 宿舍搜索 → 一键查询余额、用电趋势                    │
│  ├── 指标卡：当前余额 / 日均用电 / 预计可用天数 / 周期用电  │
│  ├── 可交互趋势图：折线+柱状，自定义用电等级               │
│  ├── 充值记录展示 + 预警状态条                            │
│  └── 内置演示数据，无校园网也可完整展示                    │
├─────────────────────────────────────────────────────────┤
│  🔔 邮件预警订阅 (subscription_alerts/)                   │
│  ├── 邮箱验证双确认 (double opt-in)                       │
│  ├── 低电量自动预警（每天最多一次）                        │
│  ├── 每日电费报告（可选）                                  │
│  ├── 一键退订链接                                          │
│  └── 测试模式：绕过校园网直接发送测试预警                   │
├─────────────────────────────────────────────────────────┤
│  ⚙️ 后端 API 代理 (server.py)                             │
│  ├── /api/status         宿舍电费查询                      │
│  ├── /api/buildings      校区楼栋列表                      │
│  ├── /api/demo-status    演示数据                          │
│  ├── /api/subscriptions  订阅管理 (POST)                   │
│  ├── /api/subscriptions/verify  邮箱验证确认                │
│  ├── /api/unsubscribe    一键退订                          │
│  ├── /api/alerts/check   手动触发预警检查                   │
│  ├── /api/version        版本信息                          │
│  └── /api/health         健康检查                          │
├─────────────────────────────────────────────────────────┤
│  🖥️ CLI 工具 (room-power-monitor/)                        │
│  ├── python -m src.cli status      宿舍电费状态            │
│  ├── python -m src.cli json        JSON 输出              │
│  └── python -m src.discover        发现 roomId            │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/jinqKing/ElectrifySZU.git
cd ElectrifySZU

# 2. 安装依赖
uv sync

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 SMTP、校园网参数等

# 4. 启动服务
uv run electrifyszu
```

打开 http://127.0.0.1:8000。不在校园网时可点击"载入演示"预览效果。

### CLI 查询

```bash
# 查询电费状态
uv run python -m src.cli status

# 输出 JSON 格式
uv run python -m src.cli json

# 发现 roomId
uv run python -m src.discover <building_id> <room_name>
```

### 运行测试

```bash
uv run pytest -v
```

## 架构

```
                    ┌──────────────┐
                    │  用户浏览器    │
                    └──────┬───────┘
                           │ HTTP
                    ┌──────▼───────┐
                    │  server.py   │  ← 线程 HTTP 服务器
                    │  API 代理     │  ← 所有响应统一 JSON
                    └──┬───┬───┬──┘
                       │   │   │
          ┌────────────┘   │   └────────────┐
          ▼                ▼                ▼
┌─────────────────┐ ┌────────────┐ ┌──────────────────┐
│ room-power-     │ │subscription│ │ web/             │
│ monitor/        │ │_alerts/    │ │ 静态文件服务      │
│                 │ │            │ │                  │
│ • DormApi 查询  │ │ • 邮箱验证 │ │ • index.html     │
│ • roomId 发现   │ │ • 预警线程 │ │ • app.js         │
│ • CLI 工具      │ │ • SMTP发送 │ │ • work-intro.html│
│                 │ │ • CSV存储  │ │                  │
└────────┬────────┘ └────────────┘ └──────────────────┘
         │
         ▼
┌─────────────────┐
│ 校园内网电费系统  │  ← 仅在校园网环境可达
└─────────────────┘
```

## 部署

### GitHub Pages（静态演示）

`web/` 目录通过 GitHub Actions 自动部署到 Pages，无需服务器即可展示仪表盘演示数据。

### 完整服务

真实查询需要将 `server.py` 部署到能访问深圳大学内网的机器上：

1. 配置 `.env` 中的 SMTP 和校园网参数
2. 运行 `uv run electrifyszu --host 0.0.0.0 --port 8000`
3. 设置 `PUBLIC_BASE_URL` 为公网地址以生成正确的邮件验证链接
4. 前端 API 指向该服务器

## 项目结构

```text
.
├── room-power-monitor/        # 电费查询核心模块
│   ├── src/
│   │   ├── api.py             # DormApi — 校园网电费接口封装
│   │   ├── cli.py             # 命令行入口
│   │   ├── config.py          # 配置管理
│   │   ├── discover.py        # roomId 自动发现
│   │   └── version.py         # 版本号
│   └── data/buildings.txt     # 校区楼栋列表
├── subscription_alerts/       # 邮件订阅预警模块
│   ├── store.py               # 订阅存储 (CSV / 线程安全)
│   ├── verification.py        # 邮箱验证流程
│   ├── alerts.py              # 预警后台线程
│   ├── email_service.py       # SMTP 发送
│   ├── email_templates.py     # 邮件模板
│   └── unsubscribe.py         # 一键退订
├── web/                       # 前端静态资源
│   ├── index.html             # 主仪表盘
│   ├── app.js                 # 前端逻辑
│   ├── styles.css             # 样式
│   ├── i18n-data.js           # 中英文文案
│   └── work-intro.html        # 团队介绍幻灯片
├── tests/                     # 测试
│   ├── test_server.py         # demo_status、buildings 解析
│   └── test_store.py          # 订阅存储 CRUD
├── server.py                  # HTTP 服务 & API 代理
├── log_config.py              # 结构化日志配置
├── SUBSCRIPTION_FLOW.md       # 订阅流程文档（含 mermaid 图）
├── CHANGELOG.md               # 变更记录
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
| GET | `/api/alerts/check` | 手动触发预警检查 |
| GET | `/api/version` | 服务版本信息 |
| GET | `/api/health` | 健康检查 |

所有响应统一格式：

```json
// 成功
{"ok": true, "data": { ... }}

// 失败
{"ok": false, "error": "人类可读消息", "hint": "建议操作", "error_code": "ROOM_NOT_FOUND"}
```

错误码：`ROOM_NOT_FOUND` · `CAMPUS_NETWORK_ERROR` · `INVALID_EMAIL` · `MISSING_FIELD` · `INVALID_THRESHOLD` · `EMAIL_DELIVERY_FAILED` · `INTERNAL_ERROR` · `NOT_FOUND`

## Matrix 团队

ElectrifySZU 由 Matrix 团队开发维护。我们也是深大学生，也在用这个工具查电费。

- 📖 [飞书项目 Wiki](https://my.feishu.cn/wiki/EuOXwd1Efi0uLCktmx7cIocynBb)
- 🎞️ [工作介绍幻灯片](web/work-intro.html)
- ⭐ 觉得有用？给个 Star 支持我们继续维护

## 许可证

MIT License © Matrix Team
