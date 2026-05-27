# ElectrifySZU 部署指南

## 架构总览

```
                            Cloudflare (www.iotun.com)
                                   │
                            ┌──────┴──────┐
                            │  公网服务器   │  &lt;PUBLIC_SERVER_IP&gt;
                            │  (Nginx)     │
                            ├──────────────┤
                            │  静态文件     │  web/ (直接读磁盘)
                            │  公共 API    │  server_public.py (:8000)
                            │  校园 API    │  → SSH 隧道 (:18080)
                            └──────┬───────┘
                                   │ SSH 隧道 (autossh -R)
                            ┌──────┴──────┐
                            │  校园网机器   │  深大内网
                            │  校园 API   │  server_campus.py (:8000)
                            │  → 192.168.84.3:9090
                            │  → 172.25.100.105:8010
                            └─────────────┘
```

---

## 目录

1. [前置条件](#1-前置条件)
2. [快速开始（本地开发）](#2-快速开始本地开发)
3. [升级到 SQLite](#3-升级到-sqlite)
4. [公网服务器部署](#4-公网服务器部署)
5. [校园网机器部署](#5-校园网机器部署)
6. [SSH 隧道搭建](#6-ssh-隧道搭建)
7. [验证部署](#7-验证部署)
8. [日常运维](#8-日常运维)
9. [回滚指南](#9-回滚指南)

---

## 1. 前置条件

### 硬件

| 节点 | 要求 | 示例 |
|:----|:-----|:-----|
| 公网服务器 | 1C2G, Linux, 公网 IP | &lt;PUBLIC_SERVER_IP&gt; (CentOS 7+) |
| 校园网机器 | 能访问校园内网, 能 SSH 出站到公网 | SZU 实验室/宿舍电脑 |

### 软件

- **Python** ≥ 3.11
- **Docker** + Docker Compose（可选，推荐）
- **Nginx**（公网服务器必须）
- **autossh**（推荐）或 rathole/frp

### 域名 & DNS

- 域名 `iotun.com` 已接入 Cloudflare（DNS 代理开启）
- 公网服务器 IP 已添加到 Cloudflare DNS 记录

---

## 2. 快速开始（本地开发）

```bash
# 克隆
git clone https://github.com/jinqKing/ElectrifySZU.git
cd ElectrifySZU

# 安装依赖
pip install uv
uv sync --extra dev

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 SMTP 和校园网配置

# 启动开发服务器（静态文件 + 所有 API）
uv run server.py --port 8000

# 访问
open http://127.0.0.1:8000
```

### 开发模式说明

```bash
# 仅公共 API（不依赖校园网）
uv run server_public.py --port 8000

# 仅校园 API（需要校园网环境）
uv run server_campus.py --port 8000

# 单体模式（全部功能，开发用）
uv run server.py --port 8000
```

### 运行测试

```bash
uv run pytest tests/ -v
```

---

## 3. 升级到 SQLite

> **版本 2.7182+** 已从 CSV/JSON 迁移到 SQLite。
> 如果是从旧版本升级，需要执行迁移。

### 3.1 迁移步骤

```bash
# 1. 备份旧数据（安全第一）
cp data/likes.json data/likes.json.bak
cp data/subscriptions.csv data/subscriptions.csv.bak

# 2. 运行迁移脚本
uv run python scripts/migrate_to_sqlite.py

# 预期输出：
#   ElectrifySZU — SQLite Migration
#   Database: data/electrifyszu.db
#   Subscriptions imported: 42
#   Likes imported: 128
#   Migration successful!

# 3. 验证数据
uv run python -c "
from electrifyszu.database import get_connection
conn = get_connection()
subs = conn.execute('SELECT COUNT(*) FROM subscriptions').fetchone()[0]
likes = conn.execute('SELECT COUNT(*) FROM likes').fetchone()[0]
print(f'Subscriptions: {subs}, Likes: {likes}')
"

# 4. 确认无误后删除旧文件
rm data/likes.json data/subscriptions.csv
```

### 3.2 数据库文件

```
data/
├── electrifyszu.db          ← SQLite 数据库（新建）
├── electrifyszu.db-wal      ← WAL 日志（SQLite 自动管理）
├── electrifyszu.db-shm      ← 共享内存（SQLite 自动管理）
├── likes.json               ← 旧 JSON（迁移后可删除）
└── subscriptions.csv        ← 旧 CSV（迁移后可删除）
```

---

## 4. 公网服务器部署

### 4.1 Docker Compose 部署（推荐）

```bash
# 在服务器上
git clone https://github.com/jinqKing/ElectrifySZU.git /opt/electrifyszu
cd /opt/electrifyszu

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 SMTP、公网 URL 等配置

# 启动
docker compose -f compose.public.yml up -d

# 查看状态
docker compose -f compose.public.yml ps
docker compose -f compose.public.yml logs -f
```

### 4.2 裸机部署

```bash
# 安装 Python 依赖
pip install httpx

# 创建数据目录
mkdir -p /opt/electrifyszu/data

# 启动公共 API 服务器（作为 systemd 服务）
cat > /etc/systemd/system/electrifyszu-public.service << 'EOF'
[Unit]
Description=ElectrifySZU Public API Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/electrifyszu
ExecStart=/usr/bin/python3 /opt/electrifyszu/server_public.py \
  --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/opt/electrifyszu/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now electrifyszu-public
```

### 4.3 Nginx 配置

Nginx 配置已位于 `deploy/nginx/electrifyszu.conf`，部署步骤：

```bash
# 复制 Nginx 配置
cp deploy/nginx/electrifyszu.conf /etc/nginx/conf.d/electrifyszu.conf

# 确保 web 目录可访问
ln -s /opt/electrifyszu/web /usr/share/nginx/html

# 测试配置
nginx -t

# 重载 Nginx
nginx -s reload
```

**配置说明：** Nginx 实现三路分流：

| 路径 | 目标 | 说明 |
|:----|:----|:----|
| `/` (静态文件) | 直接读磁盘 | HTML/JS/CSS/图片，缓存 7 天 |
| `/api/status`, `/api/buildings` | SSH 隧道 → 校园网机器 :18080 | 需要校园网访问 |
| 其他 `/api/*` | 本地 Python 服务器 :8000 | 公共 API |

---

## 5. 校园网机器部署

### 5.1 Docker Compose 部署

```bash
# 在校园网机器上
git clone https://github.com/jinqKing/ElectrifySZU.git /opt/electrifyszu
cd /opt/electrifyszu

# 配置校园网环境变量
cp .env.example .env
# 编辑 .env，填入校园 API 地址、楼栋默认值等

# 启动校园代理
docker compose -f compose.campus.yml up -d
```

### 5.2 裸机部署

```bash
# 安装依赖
pip install httpx xlrd

# 启动校园 API 服务器
cat > /etc/systemd/system/electrifyszu-campus.service << 'EOF'
[Unit]
Description=ElectrifySZU Campus API Proxy
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/electrifyszu
ExecStart=/usr/bin/python3 /opt/electrifyszu/server_campus.py \
  --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
EnvironmentFile=/opt/electrifyszu/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now electrifyszu-campus
```

### 5.3 配置示例（`.env`）

```ini
# 校园 API 配置
DORM_API_BASE=http://192.168.84.3:9090/cgcSims
DORM_CLIENT=192.168.84.87
DORM_CAMPUS_NAME=深大新斋区
DORM_BUILDING_ID=7126
DORM_BUILDING_NAME=风槐斋

# 丽湖校区 API 配置
APARTMENT_POWER_BASE=http://172.25.100.105:8010/

# 日志
LOG_LEVEL=INFO
```

---

## 6. SSH 隧道搭建

### 6.1 前提：SSH 免密登录

```bash
# 在校园网机器上
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""
ssh-copy-id user@&lt;PUBLIC_SERVER_IP&gt;

# 验证
ssh user@&lt;PUBLIC_SERVER_IP&gt; "echo 隧道就绪"
```

### 6.2 autossh（推荐，零额外依赖）

```bash
# 安装 autossh
sudo apt install autossh       # Debian/Ubuntu
sudo yum install autossh       # CentOS/RHEL

# 手动启动测试
autossh -M 0 \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -N \
  -R 18080:localhost:8000 \
  user@&lt;PUBLIC_SERVER_IP&gt;
```

#### systemd 自动启停

```bash
# 创建服务文件
sudo tee /etc/systemd/system/electrifyszu-tunnel.service << 'EOF'
[Unit]
Description=ElectrifySZU SSH Tunnel
After=network.target
Wants=network.target

[Service]
Type=simple
User=your-ssh-user
ExecStart=/usr/bin/autossh -M 0 \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -N \
  -R 18080:localhost:8000 \
  user@&lt;PUBLIC_SERVER_IP&gt;
ExecStop=/usr/bin/kill $MAINPID
Restart=always
RestartSec=10
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now electrifyszu-tunnel
sudo systemctl status electrifyszu-tunnel
```

### 6.3 方案 B：rathole（Rust 高性能）

```bash
# 公网服务器
docker run -d --name rathole --restart=always \
  -p 2333:2333 -p 18080:18080 \
  rapiz1/rathole:latest --server

# 校园网机器
docker run -d --name rathole --restart=always \
  --network host \
  rapiz1/rathole:latest --client
```

配置文件见 `deploy/tunnel/README.md`。

### 6.4 隧道验证

```bash
# 在公网服务器上检查端口
ss -tlnp | grep 18080

# 通过隧道测试校园 API
curl -s http://127.0.0.1:18080/api/health

# 通过 Nginx 测试完整链路
curl -s http://127.0.0.1/api/health
curl -s http://127.0.0.1/api/demo-status

# 测试需要校园网的端点（如果校园网机器正常运行）
curl -s "http://127.0.0.1/api/status?buildingId=7126&roomName=713&campusName=test&buildingName=test&days=30"
```

---

## 7. 验证部署

### 7.1 基本检查

```bash
# 健康检查
curl -s https://www.iotun.com/api/health
# → {"ok":true,"status":"healthy",...}

# 版本信息
curl -s https://www.iotun.com/api/version
# → {"ok":true,"version":"2.7182","python":"3.14.4"}

# 静态文件
curl -s -o /dev/null -w "%{http_code}" https://www.iotun.com/
# → 200

curl -s -o /dev/null -w "%{http_code}" https://www.iotun.com/app.js
# → 200
```

### 7.2 功能验证

```bash
# 点赞系统 (SQLite)
curl -s -X POST https://www.iotun.com/api/like/init \
  -H "Content-Type: application/json" -d '{}'
# → {"ok":true,"id":"svr-..."}

# 演示数据
curl -s https://www.iotun.com/api/demo-status | python -m json.tool

# 统计数据
curl -s https://www.iotun.com/api/stats | python -m json.tool
```

### 7.3 隧道链路验证

```bash
# 在公网服务器上测试校园 API 是否通过隧道可达
curl -s "http://127.0.0.1/api/status?buildingId=7126&roomName=713&..."
# → 如果有校园网，返回真实余额数据
# → 如果无校园网，返回 502 + 错误提示
```

---

## 8. 日常运维

### 8.1 查看日志

```bash
# Docker 日志
docker compose -f compose.public.yml logs -f --tail=100
docker compose -f compose.campus.yml logs -f --tail=100

# 隧道日志
sudo journalctl -u electrifyszu-tunnel -f

# Nginx 日志
tail -f /var/log/nginx/electrifyszu.*.log
```

### 8.2 更新部署

```bash
# 1. 拉取最新代码
cd /opt/electrifyszu
git pull

# 2. 运行迁移（如果数据库结构有变化）
uv run python scripts/migrate_to_sqlite.py

# 3. 重启服务
docker compose -f compose.public.yml restart
docker compose -f compose.campus.yml restart

# 或裸机重启
sudo systemctl restart electrifyszu-public
sudo systemctl restart electrifyszu-campus
```

### 8.3 备份

```bash
# SQLite 备份
sqlite3 data/electrifyszu.db ".backup 'data/backup/electrifyszu-$(date +%Y%m%d).db'"

# 自动备份 (cron)
echo "0 3 * * * cd /opt/electrifyszu && sqlite3 data/electrifyszu.db \
  \".backup 'data/backup/electrifyszu-\$(date +\\%Y\\%m\\%d).db'\"" \
  | crontab -
```

### 8.4 监控

```bash
# 隧道存活监控
*/5 * * * * ss -tlnp | grep 18080 > /dev/null || systemctl restart electrifyszu-tunnel

# API 健康监控
*/1 * * * * curl -sf http://127.0.0.1/api/health > /dev/null || \
  docker compose -f /opt/electrifyszu/compose.public.yml restart
```

---

## 9. 回滚指南

### 9.1 代码回滚

```bash
cd /opt/electrifyszu
git log --oneline -5
git checkout <previous-commit-hash>

# 重启服务
docker compose -f compose.public.yml down
docker compose -f compose.public.yml up -d
```

### 9.2 数据库回滚

```bash
# 如果有备份
sqlite3 data/electrifyszu.db ".restore 'data/backup/electrifyszu-20250525.db'"

# 如果需要回退到 CSV/JSON
cp data/subscriptions.csv.bak data/subscriptions.csv
cp data/likes.json.bak data/likes.json
rm data/electrifyszu.db
# 然后 checkout 旧版本代码
```

### 9.3 切换到单体模式（紧急）

```bash
# 如果隧道或校园代理出问题，可以临时切回单体模式
# 修改 Nginx 配置，把所有流量指向一个 Python 服务器
# deploy/nginx/electrifyszu.conf → 简化版本

# 启动单体服务器
docker compose up -d
```

---

## 附录

### 端口规划

| 端口 | 用途 | 绑定 |
|:----|:-----|:-----|
| 80 | Nginx HTTP | 0.0.0.0 (公网) |
| 443 | Nginx HTTPS (Cloudflare) | Cloudflare 边缘 |
| 8000 | 公网 API 服务器 | 127.0.0.1 (仅 Nginx) |
| 18080 | SSH 隧道 → 校园网 API | 127.0.0.1 (仅 Nginx) |

### 故障排查速查表

| 症状 | 可能原因 | 解决 |
|:----|:---------|:-----|
| 页面白屏，JS 报网络错误 | API 服务器未启动 | `docker compose ps` 检查 |
| `/api/status` 返回 502 | 隧道断开或校园网机器宕机 | `systemctl restart electrifyszu-tunnel` |
| 邮件发不出 | SMTP 配置错误 | 检查 `.env` 的 SMTP_* 配置 |
| 点赞不计数 | SQLite 文件权限 | `chown -R appuser:appuser data/` |
| 静态文件 404 | Nginx root 路径错误 | 检查 `deploy/nginx/electrifyszu.conf` 的 root 路径 |
