# ElectrifySZU

ElectrifySZU 是一个面向深圳大学宿舍电费余额查询与订阅预警的开源项目。当前仓库已包含可用的电费查询 Python 子模块，下一步会在其外层搭建一个便于比赛演示和同学协作的仪表盘与提醒能力。

## 当前能力

- 根据楼栋、房间号和 `roomId` 查询宿舍电费与用电记录。
- 提供命令行查询入口，支持状态、用电记录和 JSON 输出。
- 保留 `roomId` 发现工具，便于把校园电费系统里的房间参数转成程序可用配置。
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

`roomId` 与 `roomName` 必须匹配。若只知道楼栋和房间号，可先使用：

```powershell
uv run python -m src.discover --list
uv run python -m src.discover <building_id> <room_name>
```

## 项目结构

```text
.
├── room-power-monitor/      # 现有电费查询子模块
│   ├── src/                 # Python 查询、CLI、roomId 发现工具
│   ├── data/                # 楼栋列表等非敏感资料
│   └── .env.example         # 本地配置模板
├── pyproject.toml           # uv 项目配置
├── uv.lock                  # 依赖锁定文件
├── CHANGELOG.md             # 变更记录
└── LICENSE                  # MIT License
```

## 开发约定

- 真实 `.env`、抓包 HTML、数据库和临时文件不提交。
- 面向比赛演示的功能先保持小而完整，优先保证查询流程稳定。
- 重要变更记录在 `CHANGELOG.md`，便于合作者和评委追踪项目进展。

## 许可证

本项目以 MIT License 开源。
