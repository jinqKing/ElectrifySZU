# ElectrifySZU

ElectrifySZU 是一个面向深圳大学宿舍电费余额查询与订阅预警的开源项目。仓库包含静态网页仪表盘、内网 API 代理和宿舍电费查询模块：GitHub Pages 用于公开展示页面与演示数据，完整查询功能通过部署在校园内网或可访问校园电费系统的自有服务器提供。

## 当前能力

- 根据楼栋、房间号和 `roomId` 查询宿舍电费与用电记录。
- 提供命令行查询入口，支持状态、用电记录和 JSON 输出。
- 保留 `roomId` 发现工具，便于把校园电费系统里的房间参数转成程序可用配置。
- 提供可部署到 GitHub Pages 的静态仪表盘；静态页面只负责展示和演示，不直接访问校园内网接口。
- 使用 uv 管理 Python 环境，适合多人同步开发。

## 快速开始

```powershell
uv sync
Copy-Item room-power-monitor\.env.example room-power-monitor\.env
```

填写 `room-power-monitor/.env` 后运行：

```powershell
Set-Location room-power-monitor
uv run python -m src.cli status
uv run python -m src.cli json
```

启动本地仪表盘和 API 代理：

```powershell
Set-Location D:\ElectrifySZU
uv run electrifyszu
```

打开 `http://127.0.0.1:8000`。页面会通过本地 `/api/status` 代理查询校园电费接口；若暂时不在校园网，可点击“载入演示”预览仪表盘。

## 部署说明

GitHub Pages 只发布 `web/` 目录中的静态仪表盘，用于项目展示和演示数据预览。真实查询需要运行 `uv run electrifyszu`，并让该服务处在能访问深圳大学电费系统的网络环境中，例如校园内网服务器、校园网设备或合规的内网代理后方。

如果要把公开页面接入自有后端，建议让后端暴露与本项目一致的 `/api/status`、`/api/buildings` 接口，并在前端配置中指向该 API 域名。

`roomId` 与 `roomName` 必须匹配。若只知道楼栋和房间号，可先使用：

```powershell
uv run python -m src.discover --list
uv run python -m src.discover <building_id> <room_name>
```

## 项目结构

```text
.
├── room-power-monitor/      # 电费查询模块
│   ├── src/                 # Python 查询、CLI、roomId 发现工具
│   ├── data/                # 楼栋列表等非敏感资料
│   └── .env.example         # 本地配置模板
├── web/                     # 静态仪表盘页面
├── server.py                # 本地网页服务与 API 代理
├── pyproject.toml           # uv 项目配置
├── uv.lock                  # 依赖锁定文件
├── CHANGELOG.md             # 变更记录
└── LICENSE                  # MIT License
```

## 开发约定

- 真实 `.env`、抓包 HTML、数据库和临时文件不提交。
- 面向比赛演示的功能先保持小而完整，优先保证查询流程稳定。
- 项目版本以 `pyproject.toml` 为唯一来源；运行时标识和请求头从该版本自动读取。
- 重要变更记录在 `CHANGELOG.md`，便于合作者和评委追踪项目进展。

## 许可证

本项目以 MIT License 开源。
