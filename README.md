# ElectrifySZU

ElectrifySZU 是一个面向深圳大学宿舍电费余额查询与邮件预警的开源项目。当前仓库已经包含可公开部署的网页仪表盘、后端 API 代理、宿舍电费查询模块，以及基于邮件的低电量订阅与退订流程。

## 当前能力

- 根据楼栋、房间号和 `roomId` 查询宿舍电费、最近充值记录和近几日用电趋势。
- 提供 `/api/status`、`/api/buildings`、`/api/subscriptions`、`/api/unsubscribe` 等后端接口。
- 支持低电量邮件订阅、退订链接、按日限频告警检查。
- 保留 `roomId` 发现工具，便于把校园电费系统里的房间参数转换成程序配置。
- 提供静态前端仪表盘，支持中英双语、趋势图交互、单位切换、邮箱订阅入口。
- 提供 Docker / Compose 部署方式，适合放在公网服务器并通过校园内中转节点访问电费系统。

## 架构概览

最简单的本地运行模式是：

```text
浏览器 -> ElectrifySZU 后端 -> 深圳大学电费系统
```

如果要对公网开放，而电费系统只能在校内网络访问，推荐部署成：

```text
公网用户 -> Nginx -> ElectrifySZU 容器 -> 校园内中转链路 -> 电费系统
```

后端只需要能访问 `DORM_API_BASE` 指向的地址即可。这个地址可以是：

- 校园内网中的原始接口地址
- 校内机器反向映射出来的本地端口
- 你自行维护的合规内网代理

## 快速开始

### 1. 安装依赖

```powershell
uv sync
Copy-Item .env.example .env
```

### 2. 填写根目录 `.env`

根目录 `.env` 是当前项目的统一运行配置入口。最少需要配置：

```env
DORM_API_BASE=http://192.168.84.3:9090/cgcSims
DORM_CLIENT=192.168.84.87
DORM_CAMPUS_NAME=深大新斋区
DORM_BUILDING_ID=7126
DORM_BUILDING_NAME=风槐斋
DORM_ROOM_NAME=713
DORM_ROOM_ID=7322
```

如果要启用邮件订阅，还需要补充 SMTP 相关配置，见下方“邮件订阅配置”。

### 3. 运行命令行查询

```powershell
Set-Location room-power-monitor
uv run python -m src.cli status
uv run python -m src.cli json
```

如果只知道楼栋和房间号，可先用：

```powershell
Set-Location room-power-monitor
uv run python -m src.discover --list
uv run python -m src.discover <building_id> <room_name>
```

### 4. 启动本地仪表盘

```powershell
Set-Location D:\ElectrifySZU
uv run electrifyszu
```

打开 `http://127.0.0.1:8000`。如果当前环境无法访问校园电费系统，仍可点击“载入演示”预览页面效果。

## 邮件订阅配置

项目支持用户订阅低电量预警邮件，并通过退订链接自行取消提醒。需要在根目录 `.env` 中补充：

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

说明：

- `SUBSCRIPTIONS_CSV`：订阅数据文件位置，推荐在部署时持久化到宿主机目录。
- `ALERT_CHECK_TIME`：每天自动检查订阅的时间。
- `PUBLIC_BASE_URL`：邮件中的退订链接前缀，公网部署时应改成真实域名或公网地址。
- `SMTP_*` / `SENDER_*`：邮件服务器与发件人配置。

## Docker 部署

项目已提供 `Dockerfile` 和 `compose.yml`。默认采用 `host` 网络模式，便于跟随宿主机上的内网路由或本地中转端口。

```powershell
docker compose build
docker compose up -d
```

当前 `compose.yml` 还会把 `./data` 挂载到容器内 `/app/data`，用于持久化：

- 订阅 CSV
- 后续可扩展的日志或状态文件

### 推荐的公网部署方式

推荐使用：

- `Nginx` 对外暴露 80/443
- ElectrifySZU 容器只监听 `127.0.0.1:8000`
- Nginx 反代到 `127.0.0.1:8000`
- 若存在校内中转链路，则把 `DORM_API_BASE` 指向宿主机上的本地转发端口

GitHub Pages 只适合托管静态预览页面，不适合真实查询和邮件订阅。

## 项目结构

```text
.
├── room-power-monitor/      # 电费查询模块
│   ├── src/                 # Python 查询、CLI、roomId 发现工具
│   └── data/                # 楼栋列表等非敏感资料
├── subscription_alerts/     # 邮件订阅、退订与告警 worker
├── web/                     # 静态仪表盘页面
├── deploy/                  # 部署相关配置（如 Nginx 示例）
├── .env.example             # 环境变量模板
├── compose.yml              # Docker Compose 部署文件
├── Dockerfile               # 生产镜像定义
├── server.py                # API 代理与前端静态服务入口
├── pyproject.toml           # uv 项目配置
├── uv.lock                  # 依赖锁定文件
├── CHANGELOG.md             # 变更记录
└── LICENSE                  # MIT License
```

## 开发约定

- 真实 `.env`、邮件密码、抓包 HTML、数据库和临时文件不提交。
- 前端静态预览与真实查询后端要明确区分，不在 GitHub Pages 中暴露校园内网地址。
- 项目版本以 `pyproject.toml` 为唯一来源；运行时标识和请求头从该版本自动读取。
- 重要变更记录在 `CHANGELOG.md`，便于合作者和评委追踪项目进展。

## 已知限制

- `roomId` 与 `roomName` 必须匹配，输入错误会导致查询失败。
- 如果宿主机无法访问 `DORM_API_BASE`，真实查询与自动告警都不会工作。
- 当前 API 仅具备基础限流与轻量防护，公网长期运行仍建议继续补充更强的安全措施。

## 许可证

本项目以 MIT License 开源。
