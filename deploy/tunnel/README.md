# ElectrifySZU — SSH 隧道搭建指南

## 架构概览

```
用户浏览器 → Cloudflare → 公网服务器 (&lt;PUBLIC_SERVER_IP&gt;)
                              │
                    Nginx (三路分流)
                    ├── / (静态文件)         → 直接读磁盘
                    ├── /api/status 等校园API → SSH 隧道 → 校园网机器
                    └── /api/* (公共API)      → 本地 Python 服务器
```

## 方式一：autossh（推荐）

### 校园网机器上

```bash
# 安装 autossh
sudo apt install autossh   # Debian/Ubuntu
# 或
sudo yum install autossh   # CentOS/RHEL

# 建立隧道（反向代理）
autossh -M 0 \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -N \
  -R 18080:localhost:8000 \
  user@&lt;PUBLIC_SERVER_IP&gt;
```

**参数说明：**
- `-R 18080:localhost:8000` — 将校园网机器的 `:8000` 端口转发到公网服务器的 `:18080`
- `-M 0` — 禁用 autossh 监控端口（用 SSH 自身的 ServerAlive 代替）
- `ServerAliveInterval=30` — 每 30 秒发送心跳保活
- `ExitOnForwardFailure=yes` — 转发失败时退出（autossh 会自动重连）

### systemd 服务（开机自启）

创建 `/etc/systemd/system/electrifyszu-tunnel.service`：

```ini
[Unit]
Description=ElectrifySZU SSH Tunnel to Public Server
After=network.target
Wants=network.target

[Service]
User=your-ssh-user
ExecStart=/usr/bin/autossh -M 0 \
  -o "ServerAliveInterval=30" \
  -o "ServerAliveCountMax=3" \
  -o "ExitOnForwardFailure=yes" \
  -o "StrictHostKeyChecking=accept-new" \
  -N \
  -R 18080:localhost:8000 \
  user@&lt;PUBLIC_SERVER_IP&gt;
Restart=always
RestartSec=10
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now electrifyszu-tunnel
sudo systemctl status electrifyszu-tunnel
```

### SSH 密钥配置

```bash
# 在校园网机器上生成密钥（如果还没有）
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# 复制公钥到公网服务器
ssh-copy-id user@&lt;PUBLIC_SERVER_IP&gt;

# 验证免密登录
ssh user@&lt;PUBLIC_SERVER_IP&gt; "echo OK"
```

## 方式二：rathole（Rust 高性能隧道）

[rathole](https://github.com/rapiz1/rathole) 是专为内网穿透设计的 Rust 工具，比 SSH 隧道更稳定。

### 公网服务器 (`server.toml`)

```toml
[server]
bind_addr = "0.0.0.0:2333"

[server.services.campus-api]
token = "your-secret-token-here"
bind_addr = "0.0.0.0:18080"
```

### 校园网机器 (`client.toml`)

```toml
[client]
remote_addr = "&lt;PUBLIC_SERVER_IP&gt;:2333"

[client.services.campus-api]
token = "your-secret-token-here"
local_addr = "127.0.0.1:8000"
```

### Docker 方式

```bash
# 公网服务器
docker run -d --name rathole-server --restart=always \
  -p 2333:2333 -p 18080:18080 \
  -v /path/to/server.toml:/etc/rathole/server.toml:ro \
  rapiz1/rathole:latest --server /etc/rathole/server.toml

# 校园网机器
docker run -d --name rathole-client --restart=always \
  --network host \
  -v /path/to/client.toml:/etc/rathole/client.toml:ro \
  rapiz1/rathole:latest --client /etc/rathole/client.toml
```

## 方式三：frp（功能丰富）

[frp](https://github.com/fatedier/frp) 支持 Dashboard、负载均衡等高级功能。

### 公网服务器 (`frps.toml`)

```toml
[common]
bind_port = 7000
dashboard_port = 7500
dashboard_user = admin
dashboard_pwd = your-password
```

### 校园网机器 (`frpc.toml`)

```toml
[common]
server_addr = &lt;PUBLIC_SERVER_IP&gt;
server_port = 7000

[campus-api]
type = tcp
local_ip = 127.0.0.1
local_port = 8000
remote_port = 18080
```

## 验证隧道是否工作

在公网服务器上：

```bash
# 检查端口是否在监听
ss -tlnp | grep 18080

# 测试 campus 代理是否可达
curl -s http://127.0.0.1:18080/api/health

# 通过 Nginx 测试完整链路
curl -s http://127.0.0.1/api/health
curl -s http://127.0.0.1/api/demo-status
```

## 故障排查

| 问题 | 可能原因 | 解决方法 |
|------|---------|---------|
| 隧道端口不在监听 | SSH 连接断开 | `systemctl restart electrifyszu-tunnel` |
| `/api/status` 返回 502 | 校园网机器上的 Python 进程挂了 | `docker restart electrifyszu-campus` |
| 隧道频繁断开 | 网络不稳定 | 减小 `ServerAliveInterval` 到 15 |
| 公钥认证失败 | 密钥未正确配置 | 重新执行 `ssh-copy-id` |
