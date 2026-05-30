# ElectrifySZU 安全修复路线图

> 基于 2026-05-31 全面安全审查生成，按优先级排序。

## 第一阶段：高危 — 信息泄露与注入

### 1.1 脱敏 CAMPUS_GROUP 中的内网 IP

**文件:** `electrifyszu/config.py:103-108`

**问题:** 四个校园网 client IP 硬编码在源码中，并通过 API 响应返回给前端。

**方案:**

- [ ] 将 `CAMPUS_GROUP` 从硬编码字典改为从环境变量加载
- [ ] 添加 `CAMPUS_CLIENT_LIHU`、`CAMPUS_CLIENT_YUEHAI_NORTH` 等环境变量
- [ ] 提供带默认值（留空）的回退，生产环境强制要求配置
- [ ] API 响应中将 `client` 字段替换为 `campus_group` 标识名（如 `yuehai_north`），不再返回原始 IP
- [ ] 同步更新 `.env.example`，添加注释说明

**影响范围:**
- `electrifyszu/config.py` — `CAMPUS_GROUP` 定义
- `electrifyszu/server/handlers/status.py:67,115` — API 响应中的 client 字段
- `electrifyszu/server/handlers/demo.py:77` — 演示数据中的硬编码 IP
- `electrifyszu/server/handlers/buildings.py:14-17` — `_campus_group()` 函数
- `web/modules/buildings.js` — 前端 campus 筛选逻辑（确认是否依赖 IP 值）

### 1.2 脱敏注释和文档中的内网地址

**文件:** `server_campus.py`, `electrifyszu/apartment/api.py`, `compose.campus.yml`

**问题:** 源代码注释中直接写出了 dorm power system 和 apartment power system 的内网 URL。

**方案:**

- [ ] `server_campus.py:31-32` — 替换为 `$DORM_API_BASE` 和 `$APARTMENT_POWER_BASE` 占位符
- [ ] `electrifyszu/apartment/api.py:57` — docstring 中移除具体 URL
- [ ] `compose.campus.yml:5-6` — 同上处理

### 1.3 修复前端 XSS — `highlightBuildingText` 的 innerHTML 注入

**文件:** `web/modules/buildings.js:223,235-238`

**问题:** `highlightBuildingText` 将用户搜索关键字包裹在 `<mark>` 标签中但未对原始文本做 HTML 转义，随后通过 `innerHTML` 渲染。

**方案:**

- [ ] 在 `highlightBuildingText` 中，先用 `escapeHtml()` 转义 `text` 再执行高亮替换
- [ ] 在 `renderBuildingOptionsForList` 中，对 `campusInfo` 也调用 `escapeHtml()`
- [ ] 审计 `buildings.js` 中所有 `innerHTML` 赋值点，确保数据来源安全

---

## 第二阶段：中危 — 输入验证与配置加固

### 2.1 服务端对 `days` 参数添加上限

**文件:** `electrifyszu/server/handlers/status.py:43`

**问题:** `days` 参数从查询字符串读取，无服务端上限（前端 `max="180"` 可被绕过）。

**方案:**

- [x] 在所有 handler 的 `int(query_value(query, "days") or "30")` 后添加 `min(max(days, 1), 365)`
- [x] 同步检查 `alerts.py` 中 `run_once` 的 `days` 使用（硬编码 30，无需改动）

### 2.2 HTTP_PROXY 环境变量白名单校验

**文件:** `electrifyszu/dorm/api.py:46-49`, `electrifyszu/dorm/discover.py:68`

**问题:** `HTTP_PROXY` 环境变量可被恶意修改，将校园网 API 请求重定向。

**方案:**

- [x] 添加 `is_safe_proxy_url(url)` 校验函数，仅允许 `127.0.0.1` / 内网 IP 范围的代理
- [x] 添加 `ALLOWED_PROXY_HOSTS` 环境变量白名单
- [x] 在日志中记录使用的代理地址

### 2.3 Docker 安全加固

**文件:** `compose.yml`, `compose.public.yml`, `Dockerfile`

**问题:** `.env` 挂载未设只读；健康检查内联 Python 代码。

**方案:**

- [x] `compose.yml` — `security_opt: no-new-privileges:true` + `cap_drop: ALL` + host 网络注释
- [x] `compose.public.yml` — 两个 service 添加 security_opt + cap_drop
- [x] `compose.campus.yml` — security_opt + cap_drop + host 网络注释
- [x] `deploy/campus/Dockerfile` — 新增 HEALTHCHECK
- [ ] `Dockerfile` — 健康检查改用 `curl` 或预编译的简单 HTTP 客户端（可选）

### 2.4 添加 Python 层面速率限制

**文件:** `server.py`, `server_public.py`

**问题:** Nginx 有 `limit_req`，但直接访问 Python 端口时无速率保护。

**方案:**

- [x] 新建 `electrifyszu/server/rate_limit.py` — 基于 deque 的滑动窗口限流器
- [x] 在 `server.py` / `server_public.py` / `server_campus.py` 的 do_GET/do_POST 入口集成
- [x] `/api/status` 10次/60s，`/api/subscriptions` 5次/60s，POST 通用 30次/60s，默认 60次/60s

---

## 第三阶段：低危 — 安全头与信息加固

### 3.1 添加安全响应头

**文件:** `server.py`, `server_public.py`, `server_campus.py`, `deploy/nginx/electrifyszu.conf`

**问题:** 缺少 `X-Content-Type-Options`、`X-Frame-Options`、`CSP` 等安全头。

**方案:**

- [x] Python — 在 7 个响应发送点统一添加 `X-Content-Type-Options: nosniff` + `X-Frame-Options: DENY`
- [x] Nginx — server 块添加 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`
- [ ] Nginx — 考虑添加基础 `Content-Security-Policy`（后续单独规划）

### 3.2 ~~隐藏 Server 版本头~~（跳过—用户保留版本号作为特色）

**文件:** `server.py:63`, `server_public.py:77`, `server_campus.py:51`

**问题:** `server_version` 暴露了具体版本号。

**方案:**

- [ ] 生产模式下设置 `server_version = "ElectrifySZU"`（不含版本号）
- [ ] 或通过 `ELECTRIFYSZU_ENV=production` 环境变量控制

### 3.3 演示数据中移除真实内网 IP

**文件:** `electrifyszu/server/handlers/demo.py:74-114`

**问题:** `demo_status()` 返回的硬编码数据中包含真实 client IP `192.168.84.87`。

**方案:**

- [x] 将 `demo.py` 中的 `client` 字段改为 campus group 标识名（已在阶段一完成）

### 3.4 加固 `validate_same_origin` 的宽松回退

**文件:** `electrifyszu/server/middleware.py:31`

**问题:** 缺少 Origin 和 Referer 头时直接返回 `True`。

**方案:**

- [x] 为非浏览器客户端添加注释说明 + DEBUG 日志，保持行为不变

---

> **额外发现 (2026-05-31)**：MTT 服务器上 Cloudflare Tunnel 的 token 可通过 `docker inspect` 在命令行参数中查看。属于宿主机权限泄露——任何能执行 docker 命令的用户都可获取该 token。建议改用 Docker secret 或环境变量注入 token。

## 第四阶段：持续安全实践

### 4.1 完善 `.env.example`

- [x] 重写 .env.example：分组索引 + [必需]/[可选]/[仅测试] 标签 + 补充公寓变量和 DB_PATH + 移除无用 TEST_* 变量

### 4.2 添加安全测试用例

- [x] `tests/test_server_security.py` 中补充: days 上限、内网 IP 不泄露、代理白名单、速率限制测试（阶段一二三已完成）

### 4.3 依赖审计

- [ ] 定期运行 `uv pip list --outdated` 检查过时依赖
- [ ] 关注 `httpx` 和 `xlrd` 的安全公告

---

## 修复顺序建议

```
第1周:  1.1 → 1.2 → 1.3    (高危三件)
第2周:  2.1 → 2.2 → 3.3    (输入验证 + 演示数据脱敏)
第3周:  2.3 → 2.4 → 3.1    (Docker + 速率限制 + 安全头)
第4周:  3.2 → 3.4 → 4.1    (版本头 + origin 加固 + 文档)
```

> 完成每阶段后在对应复选框打勾，提交到 `deploy/docker-mtt` 分支验证。
