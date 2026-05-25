# Configuration Guide

Master reference for all environment variables, CLI arguments, and ready-made deployment profiles.

## Environment Variable Catalog

Variables are read from `.env` in the project root. Values in `.env` are **never overwritten** if already set in the OS environment (explicit shell export takes precedence).

### Core Service

| Variable | Default | Description |
|----------|---------|-------------|
| *(—)* | | No env var; controlled by CLI `--host` / `--port` |
| `LOG_LEVEL` | `INFO` | Console log verbosity: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_DIR` | `logs` | Log file directory (absolute or relative to project root) |
| `LOG_MAX_BYTES` | `10485760` | Single log file size before rotation (bytes; default 10 MiB) |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated backup files retained |

### Dorm Campus System (粤海 / 北 / 南 / 新斋区)

| Variable | Default | Description |
|----------|---------|-------------|
| `DORM_API_BASE` | `http://192.168.84.3:9090/cgcSims` | Campus power-system endpoint (without trailing slash) |
| `DORM_CLIENT` | `192.168.84.87` | Client IP identifying this campus network segment |
| `DORM_CAMPUS_NAME` | `深大新斋区` | Human-readable campus name shown in UI |
| `DORM_BUILDING_ID` | `7126` | Numeric building identifier for default room |
| `DORM_BUILDING_NAME` | `风槐斋` | Default building display name |
| `DORM_ROOM_ID` | `7322` | Fallback roomId (auto-discovered normally; useful for scripts) |
| `DORM_ROOM_NAME` | `713` | Default room number |
| `DORM_POLL_INTERVAL` | `3600` | Reserved for future polling features (seconds) |
| `DORM_LOW_POWER_THRESHOLD` | `20` | Default kW·h threshold for new subscriptions |
| `HTTP_PROXY` | _(unset)_ | Proxy for outbound HTTP requests (`http://host:port`). Leave blank for direct connections. Needed when accessing internet from behind GFW. |

### Apartment System (丽湖 West Lake)

| Variable | Default | Description |
|----------|---------|-------------|
| `APARTMENT_POWER_BASE` | `http://172.25.100.105:8010/` | ASP.NET apartment power portal URL |
| `APARTMENT_BUILDING_CODE` | `01` | Default apartment building code |
| `APARTMENT_ROOM_NAME` | `501` | Default apartment room number |
| `APARTMENT_POWER_TIMEOUT` | `15` | HTTP request timeout in seconds |
| `APARTMENT_LOW_POWER_THRESHOLD` | `20` | Default kW·h threshold for apartment subscriptions |

Supported buildings: 梧桐树#(`01`), 青冈栎#(`02`), 三角梅#(`03`), 冬青树#(`04`), 紫罗兰#(`05`), B3文韬楼#(`06`).

### Subscription & Alerts

| Variable | Default | Description |
|----------|---------|-------------|
| `SUBSCRIPTIONS_CSV` | `data/subscriptions.csv` | Path to subscriber database (accepts relative paths) |
| `ALERT_CHECK_TIME` | `08:00` | Time of day for automatic daily alert sweeps (`HH:MM`) |
| `ALERT_LOOP_INTERVAL` | `300` | Sleep interval between wake-ups in production mode (seconds; ≥ 30) |
| `ALERT_MODE` | `production` | `production` = schedule-driven; `testing` = continuous loop ignoring clock |
| `ALERT_TEST_INTERVAL` | `300` | Interval used when `ALERT_MODE=testing` (≥ 10 seconds) |
| `SKIP_RECENT` | `1` | When `testing` mode: skip subscriptions already alerted today (`0` = force repeat) |
| `FORCE_SEND_ALERT` | `0` | When `testing` mode: inject synthetic low-balance data, bypass campus API |
| `FORCE_SEND_DAILY_REPORT` | `0` | When `testing` mode: force daily-report generation |
| `ALLOWED_EMAIL_DOMAINS` | `@email.szu.edu.cn,@mails.szu.edu.cn` | Comma-separated email domain whitelist for subscriptions |
| `PUBLIC_BASE_URL` | _(empty)_ | Absolute base URL used in verification/unsubscribe email links |
| `ALERT_ADMIN_TOKEN` | _(empty)_ | Secret token for `POST /api/alerts/check`. Generate with: `python -c "import secrets;print(secrets.token_hex(16))"` |

### SMTP Mail Delivery

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | _(required)_ | SMTP server hostname (rejected if still `smtp.example.com`) |
| `SMTP_PORT` | `465` | SMTP port |
| `SMTP_SSL` | `true` | Connect via implicit TLS |
| `SMTP_STARTTLS` | `false` | Upgrade plain TCP to TLS (use with port 587) |
| `SENDER_EMAIL` | _(required)_ | Sender address (rejected if ends with `@example.com`) |
| `SENDER_PASSWORD` | _(required)_ | Authorization code/password (rejected if equals placeholder) |
| `SENDER_NAME` | `电费预警系统` | Display name in "From:" header |

### Email Appearance

| Variable | Default | Description |
|----------|---------|-------------|
| `EMAIL_SIGNATURE` | _(empty)_ | Text appended to bottom of every email (supports `\n` escape) |
| `EMAIL_SUBJECT_PREFIX` | _(empty)_ | Tag prepended to every subject line (e.g. `[ElectrifySZU]`) |

### Test-Mail Defaults

Used by `electrifyszu-delivery-test` CLI when corresponding flags are omitted.

| Variable | Default |
|----------|---------|
| `TEST_RECIPIENT_EMAIL` | `test@example.com` |
| `TEST_EMAIL_SUBJECT` | `电费预警通知` |
| `TEST_EMAIL_CONTENT` | `这是一封测试邮件。` |
| `TEST_BUILDING_CAMPUS` | `粤海` |
| `TEST_BUILDING_NAME` | `风槐斋` |
| `TEST_ROOM_NAME` | `713` |
| `TEST_CLIENT_IP` | `192.168.84.87` |

---

## Scenario Profiles

Copy-paste-ready configurations for common setups. Commented lines indicate safe defaults.

### Profile A: Local Development

Full stack on laptop, connected to campus Wi-Fi.

```ini
DORM_API_BASE=http://192.168.84.3:9090/cgcSims
DORM_CLIENT=192.168.84.87
DORM_CAMPUS_NAME=深大新斋区
DORM_BUILDING_ID=7126
DORM_BUILDING_NAME=风槐斋
DORM_ROOM_NAME=713

# Debug-mode logging
LOG_LEVEL=DEBUG

# Local loopback for emails (won't deliver; for verifying SMTP config only)
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_SSL=false
SENDER_EMAIL=you@localhost
SENDER_PASSWORD=password
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

Start: `uv run server.py --port 8000`

---

### Profile B: Campus LAN Deployment

Machine plugged into campus wired network, accessible by students on WiFi.

```ini
DORM_API_BASE=http://192.168.84.3:9090/cgcSims
DORM_CLIENT=192.168.84.87
DORM_CAMPUS_NAME=深大新斋区
DORM_BUILDING_ID=7126
DORM_BUILDING_NAME=风槐斋
DORM_ROOM_NAME=713

# Real SMTP
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_SSL=true
SENDER_EMAIL=your_mail@qq.com
SENDER_PASSWORD=abcdefghijklmnop
PUBLIC_BASE_URL=http://YOUR_CAMPUS_IP:8000
ALERT_ADMIN_TOKEN=$(random_secret_here)
```

Start: `uv run server.py --host 0.0.0.0 --port 8000`

---

### Profile C: Public Internet + Nginx Reverse Proxy

Container behind Nginx, reachable worldwide. Campus API accessed via SSH tunnel or frp relay from a campus-hosted relay machine.

```ini
# Tunnel forwards campus port to localhost
DORM_API_BASE=http://127.0.0.1:9090/cgcSims
DORM_CLIENT=192.168.84.87
DORM_CAMPUS_NAME=深大新斋区
DORM_BUILDING_ID=7126
DORM_BUILDING_NAME=风槐斋
DORM_ROOM_NAME=713

# Add LiHu campus too (relay separately)
APARTMENT_POWER_BASE=http://127.0.0.1:8010/

SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_SSL=true
SENDER_EMAIL=notify@gmail.com
SENDER_PASSWORD=app_specific_password
SENDER_NAME=Matrix电费预警

PUBLIC_BASE_URL=https://www.iotun.com
ALERT_ADMIN_TOKEN=$(random_secret_here)

LOG_LEVEL=INFO
LOG_DIR=/var/log/electrifyszu
```

Nginx points upstream to `127.0.0.1:8000`. See `deploy/nginx/electrifyszu.conf`.

---

### Profile D: GitHub Pages Frontend + Separate Backend

Static dashboard served from `jinqking.github.io/ElectrifySZU`, API hosted elsewhere.

Requirements:
1. Backend must enable CORS (configure Nginx `Access-Control-Allow-Origin: https://jinqking.github.io`).
2. Backend must set `PUBLIC_BASE_URL=https://BACKEND.DOMAIN.COM` (where email callbacks resolve).
3. Frontend `web/modules/config.js` must define `BASE_URL` pointing to the backend API origin.

```ini
# === BACKEND .env ===
DORM_API_BASE=http://RELAY_LOCALHOST:9090/cgcSims
DORM_CLIENT=192.168.84.87
DORM_CAMPUS_NAME=深大新斋区
DORM_BUILDING_ID=7126
DORM_BUILDING_NAME=风槐斋
DORM_ROOM_NAME=713

SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_SSL=true
SENDER_EMAIL=your_mail@qq.com
SENDER_PASSWORD=auth_code
PUBLIC_BASE_URL=https://backend.yourdomain.com
ALERT_ADMIN_TOKEN=$(secret)
```

```javascript
// === FRONTEND web/modules/config.js ===
window.ELECTRIFY_CONFIG = {
  BASE_URL: "https://backend.yourdomain.com",
};
```

Push `web/` to `master` → GitHub Actions deploys Pages automatically.

---

### Profile E: Testing Mode (Offline Alert Verification)

Verify alert pipelines without campus network access. Fabricated data injected.

```ini
ALERT_MODE=testing
ALERT_TEST_INTERVAL=60
SKIP_RECENT=0
FORCE_SEND_ALERT=1
FORCE_SEND_DAILY_REPORT=1

# Still needs real SMTP for delivery verification
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_SSL=true
SENDER_EMAIL=you@qq.com
SENDER_PASSWORD=auth_code
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

With this profile, `AlertRunner.run_once()` produces fake low-balance data and sends real emails to subscribed addresses. Useful for validating SMTP creds, email templates, and unsubscribe links.

---

## CLI Arguments

`uv run server.py` accepts positional arguments that override env-based defaults:

| Flag | Default | Description |
|------|---------|-------------|
| `--host HOST` | `127.0.0.1` | Bind address |
| `--port PORT` | `8000` | Listen port |
| `--check-now` | disabled | Execute one alert sweep before starting HTTP listener |
| `--no-skip` | disabled | Don't skip subscriptions already alerted today |

Combined example:

```bash
uv run server.py --host 0.0.0.0 --port 9090 --check-now
```

Additional CLI entry points defined in `pyproject.toml`:

| Script Alias | Target | Purpose |
|--------------|--------|---------|
| `electrifyszu` | `server:main` | Launch HTTP dashboard server |
| `electrifyszu-delivery-test` | `electrifyszu.subscription.test_delivery:main` | Standalone email delivery test |

---

## Configuration Resolution Order

When multiple sources define the same setting:

```
Shell env ($VAR)  >  .env file  >  Code default
```

Specifically:
- `load_dotenv()` inserts keys into `os.environ` only if not already present (**never overwrites**).
- CLI `--host` / `--port` always win over anything in `.env`.
- `PUBLIC_BASE_URL` env var overrides request-derived base URL for email links.
