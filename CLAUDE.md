# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 语言偏好

始终使用中文回复。

## 本地开发环境

Conda 环境：`D:\anaconda3\envs\electrifyszu`。运行命令前先激活：`conda activate electrifyszu`，或直接用该环境的 Python 解释器：`D:\anaconda3\envs\electrifyszu\python.exe`。

## 生产环境

远程linux服务器连接方式：ssh mtt
远程项目文件夹：~/ElectrifySZU
部署方式：docker

## 常用命令

```bash
# 开发服务器（自动选择空闲端口）
python server.py --port 8000

# 运行全部测试
python -m pytest

# 运行单个测试文件
python -m pytest tests/test_server_security.py

# Docker 构建并启动
docker compose up --build -d

# Docker 查看日志
docker logs -f electrifyszu

# 部署到 MTT 服务器
ssh mtt "cd /root/ElectrifySZU && git pull && docker compose up --build -d"
```

## 架构概览

**Python 纯标准库 HTTP 服务器** + **零框架 ES modules SPA**。没有第三方 Web 框架，没有前端打包工具。

### 远程仓库地址

https://github.com/jinqKing/ElectrifySZU

### 请求路由

`electrifyszu/server/router.py` 中 `ROUTES` 字典定义 `(method, path) → (module_name, function_name)`。`server.py` 的 `DashboardHandler.do_GET/do_POST` 通过 `importlib.import_module` 懒加载 handler 模块，未匹配路由回退到 `serve_static()` 从 `web/` 提供静态文件。

添加新 API 端点的步骤：
1. 在 `electrifyszu/server/handlers/<name>.py` 中编写 handler 函数
2. 在 `router.py` 的 `ROUTES` 字典中注册 `(method, path)` 映射

### Handler 规范

所有 handler 函数签名：`def handle_xxx(handler: BaseHTTPRequestHandler, query: dict[str, list[str]] | None = None) -> None`。`types.py` 定义了 `Handler` 协议和全部工具函数 (`send_json`, `send_error`, `read_request_data`, `query_value` 等)。

### 前端架构

`web/` 目录下 `index.html` + ES modules (`web/modules/`)。无打包步骤。关键模块：

- **`api.js`**: `fetchJson`/`postJson` 封装了 30s 超时 (`AbortController`)、JSON 验证、`response.ok` 检查、`err.status` 传递
- **`api.js`** 中的 `canUseBackend()` 用于判断是否有后端可用（GitHub Pages 静态页面场景下降级）
- **`i18n.js`**: `t()` 翻译函数，`data-i18n` 属性驱动的前端国际化
- **`likes.js`**: 点赞模块，含 400 重试逻辑（`_likePending` 防并发，`_retried` 防无限递归）
- **`state.js`**: 共享可变状态

前端 API 基础 URL 可通过 `window.ELECTRIFYSZU_API_BASE` 或 `window.__SERVER_CONFIG__` 注入。

### 数据持久化

所有运行时数据存储在 `data/` 目录（Docker 中通过 volume 挂载到 `/app/data`）：

| 文件 | 用途 | 存储引擎 |
|------|------|---------|
| `data/likes.db` | 点赞 ID、点赞状态 | SQLite (WAL 模式) |
| `data/subscriptions.csv` | 邮件订阅 | CSV (tempfile + fsync + rename 原子写入) |

`ELECTRIFYSZU_DATA_DIR` 环境变量控制数据目录位置（默认在包目录下，Docker 中设为 `/app/data`）。

### database.py 连接管理

`get_connection()` 返回线程本地连接，WAL 模式 + `busy_timeout=5000`。`ELECTRIFYSZU_DB_PATH` 环境变量控制数据库路径。DB 文件不存在时自动创建并建表，存在旧 `likes.json` / `subscriptions.csv` 时自动迁移。

### 邮件预警系统

`AlertRunner` 在守护线程中运行。生产模式等到 `ALERT_CHECK_TIME`（默认 08:00）触发；测试模式每隔 `ALERT_LOOP_INTERVAL` 秒循环。房间数据按 (client, campus, building, room) 键去重获取，同一房间的多个订阅者共享一次 API 调用。

### Docker 部署

`compose.yml` 使用 `network_mode: host`（需要直接访问校园网）。非 root 用户 `appuser` 运行。健康检查通过 `/api/demo-status` 端点。

## 关键约定

- 包管理器为 `uv`，锁文件为 `uv.lock`，Python 版本要求 `>=3.11`（`.python-version` 为 `3.14`）
- 生产依赖仅 `httpx` 和 `xlrd`，无其他第三方库
- 所有 POST 请求需要同源验证 (`validate_same_origin`)，检查 `Origin`/`Referer` 是否匹配 `Host`
- Docker 中数据持久化路径为 `/app/data/`，通过 `ELECTRIFYSZU_DATA_DIR` 环境变量控制
- Git 提交信息使用中文，格式为 `<type>(<scope>): <description>`，如 `fix(likes): ...`，而且提交时不要带claude。
- 当处于 worktree 环境并需要展示页面时，使用 `uv run server.py --port <未占用端口>` 启动预览服务，每次都要确认端口不冲突
- 部署前先推到 `deploy/docker-mtt` 分支在 MTT 服务器上验证，确认无误后再合并到 `master`
