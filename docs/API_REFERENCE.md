# API Reference

Complete specification for all ElectrifySZU REST endpoints.

## Quick Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/status` | none | Query dorm electric balance & trends |
| GET | `/api/buildings` | none | Campus & building list |
| GET | `/api/building-ranking` | none | Floor power consumption leaderboard |
| GET | `/api/apartment/floors` | none | Apartment floor list (丽湖) |
| GET | `/api/apartment/rooms` | none | Apartment room list (丽湖) |
| GET | `/api/demo-status` | none | Offline demo data |
| POST | `/api/subscriptions` | none (+ XSRF) | Create low-balance subscription |
| GET | `/api/subscriptions/verify` | none | Confirm subscription via token |
| GET | `/api/unsubscribe` | none | Cancel subscription via token |
| POST | `/api/alerts/check` | **admin** | Trigger immediate alert sweep |
| POST | `/api/archive/batch` | **admin** | Trigger batch collection of overdue rooms |
| GET | `/api/archive/status` | **admin** | Archive table row counts + recent runs |
| GET | `/api/archive/history` | **admin** | Historical trend & charges for a room |
| POST | `/api/like/init` | none (+ XSRF) | Issue unique like identity |
| POST | `/api/like` | none (+ XSRF) | Submit a like |
| GET | `/api/like/count` | none | Total like count |
| GET | `/api/like/my` | none | Has current ID already liked? |
| GET | `/api/stats` | none | Aggregate statistics |
| GET | `/api/version` | none | Service version info |
| GET | `/api/health` | none | Health-check probe |
| GET | `/api/github-stars` | none | Repo star count (cached) |

Auth legend: `none` = open, `(+ XSRF)` = same-origin enforced, `**admin**` = `X-Admin-Token` required.

---

## Response Convention

Every endpoint returns JSON wrapped in a standard envelope:

### Success

```json
{"ok": true, "data": {...}, "message": "...optional..."}
```

### Error

```json
{"ok": false, "error": "Human-readable message", "hint": "Action suggestion", "error_code": "SHORT_CODE"}
```

All responses carry `Referrer-Policy: no-referrer` header.

---

## Error Code Registry

| Code | HTTP | Meaning | Where |
|------|------|---------|-------|
| `ROOM_NOT_FOUND` | 502 | roomId/roomName mismatch or undiscoverable | `/api/status` |
| `CAMPUS_NETWORK_ERROR` | 502 | Cannot reach campus intranet API | `/api/status`, alerts |
| `BUILDING_NOT_FOUND` | 404 | Unknown apartment building code | `/api/apartment/floors`, `/api/apartment/rooms` |
| `FORBIDDEN_ORIGIN` | 403 | Cross-site POST detected | all POST endpoints |
| `UNAUTHORIZED` | 401 | Invalid/missing `X-Admin-Token` | `/api/alerts/check` |
| `ADMIN_AUTH_REQUIRED` | 401 | Missing/invalid `X-Admin-Token` on archive endpoint | `/api/archive/*` |
| `NOT_FOUND` | 404 | No route matches | all unmatched POST |
| `INVALID_EMAIL` | 400 | Malformed email address | `/api/subscriptions` |
| `INVALID_EMAIL_DOMAIN` | 400 | Domain not in allow-list | `/api/subscriptions` |
| `MISSING_FIELD` | 400 | Required input absent | `/api/subscriptions` |
| `INVALID_THRESHOLD` | 400 | Threshold ≤ 0 or > 10000 | `/api/subscriptions` |
| `INVALID_INPUT` | 400 | Other validation failure | `/api/subscriptions` |
| `EMAIL_DELIVERY_FAILED` | 502 | SMTP delivery error | `/api/subscriptions` |
| `INTERNAL_ERROR` | 500 | Unexpected server exception | `/api/subscriptions` |
| `INVALID_LIKE_ID` | 400 | Bad `svr-*` format | `/api/like`, `/api/like/my` |
| `UNKNOWN_LIKE_ID` | 400 | ID never issued by this server | `/api/like` |
| `INVALID_CONTENT_LENGTH` | 400 | Non-numeric Content-Length | all POST |
| `REQUEST_TOO_LARGE` | 413 | Body exceeds 64 KB | all POST |
| `INVALID_JSON` | 400 | Malformed JSON body | all POST (json) |
| `INVALID_FORM_BODY` | 400 | Undecodable form body | all POST (form) |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Unknown Content-Type | all POST |

---

## Endpoint Details

### Archive Admin

#### `POST /api/archive/batch`

Trigger synchronous batch collection of all overdue rooms. Requires authentication.

**Auth:** Header `X-Admin-Token` must match `ALERT_ADMIN_TOKEN` env var.

**Success Response**

```json
{
  "ok": true,
  "queued": 5,
  "done": 4,
  "failed": 1,
  "elapsed_s": 12.3
}
```

Internally calls `enqueue_from_subscriptions()` to register any newly subscribed rooms, then drains all pending collection tasks, disabling tasks with >5 consecutive failures.

---

#### `GET /api/archive/status`

Report archive table sizes and recent collection runs. Requires authentication.

**Auth:** Header `X-Admin-Token`.

**Success Response**

```json
{
  "ok": true,
  "tables": {
    "room_mappings": 42,
    "room_snapshots": 156,
    "daily_consumption": 2890,
    "charge_events": 34,
    "collection_tasks": 12,
    "collection_runs": 8
  },
  "table_count": 6,
  "oldest_snapshot": "2026-05-20T10:00:00",
  "newest_snapshot": "2026-05-27T22:00:00",
  "recent_runs": []
}
```

---

#### `GET /api/archive/history`

Browse historical consumption data for a given room. Requires authentication.

**Auth:** Header `X-Admin-Token`.

**Parameters**

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `buildingId` | string | yes | — | Building identifier |
| `roomName` | string | yes | — | Room number |
| `source` | string | no | `dorm` | `dorm` or `apartment` |
| `client` | string | no | from `.env` | Campus client IP |
| `days` | integer | no | `30` | Days of historical trend to return |

**Success Response**

```json
{
  "ok": true,
  "building_id": "7126",
  "room_name": "713",
  "trend": [
    { "date": "2026-05-14", "daily_used_kwh": 1.5, "remaining": 27.8 }
  ],
  "latest_snapshot": {
    "captured_at": "2026-05-27T18:00:00",
    "remaining": 18.6,
    "total_used_kwh": 42.8,
    "daily_avg_kwh": 1.43,
    "est_days_left": 13.0,
    "status": "low"
  },
  "recent_charges": []
}
```

---

### Dorm Status

#### `GET /api/status`

Query electric balance, 30-day trend, and recharge records for a dorm room.

**Cache strategy:** Cache-first. Tries SQLite snapshot <24h old first; on hit, returns immediately with `_source: "cache"`. On miss, performs live campus-api fetch, persists to archive, and returns with `_source: "live"`.

**Parameters**

**Parameters**

| Name | Type | Source | Required | Default | Description |
|------|------|--------|----------|---------|-------------|
| `client` | string | query | yes¹ | from `.env` | Client IP identifying the campus network segment |
| `campusName` | string | query | yes¹ | from `.env` | Display name of the campus |
| `buildingId` | string | query | yes¹ | from `.env` | Numeric building identifier |
| `buildingName` | string | query | yes¹ | from `.env` | Display name of the building |
| `roomName` | string | query | yes² | from `.env` | Room number (e.g. `"713"`) |
| `days` | integer | query | no | `30` | Number of historical days to retrieve |

> ¹ Falls back to defaults from `.env` if omitted entirely.  
> ² Must exactly match the physical room number.

**Success Response**

```json
{
  "ok": true,
  "data": {
    "building_id": "7126",
    "client": "192.168.84.87",
    "campus_name": "深大新斋区",
    "building_name": "风槐斋",
    "room_id": "7322",
    "room_name": "713",
    "period": { "begin": "2026-04-20", "end": "2026-05-20", "days": 30 },
    "records": 30,
    "threshold_kwh": 20,
    "status": "low",
    "remaining": 18.6,
    "total_used_kwh": 42.8,
    "daily_avg_kwh": 1.43,
    "est_days_left": 13.0,
    "last_record": "2026-05-20",
    "_source": "live",
    "_captured_at": "2026-05-27T18:00:00",
    "building_percentile": 72,
    "building_rank": 28,
    "building_rank_total": 39,
    "trend": [
      { "date": "2026-05-14", "remaining": 27.8, "daily_used_kwh": 1.5 },
      /* ... */
    ],
    "recharges": [
      { "time": "2026-05-08", "kwh": 50, "yuan": 30.5, "method": "微信支付" },
      /* ... */
    ]
  }
}
```

Fields `building_percentile`, `building_rank`, `building_rank_total` are present only when ranking cache exists for the queried building.
Fields `_source` (`"cache"` or `"live"`) and `_captured_at` (ISO timestamp) indicate data provenance and are present when served from the Power Archive cache.

**Notes**

- Requests with `client=172.21.101.11` and `buildingId` in `{01..06}` automatically route to the apartment (丽湖) subsystem.
- Cache-first strategy: SQLite snapshot <24h old is served without any campus-network round-trip. On cache miss, live fetch runs and result is persisted.
- Requires connectivity to the campus intranet API at `DORM_API_BASE` (for cache misses).

---

#### `GET /api/buildings`

Returns the full campus-and-building hierarchy.

**Parameters:** None.

**Success Response**

```json
{
  "ok": true,
  "data": [
    {
      "client": "192.168.84.87",
      "name": "深大新斋区",
      "buildings": [
        { "id": "7126", "name": "风槐斋" },
        { "id": "7127", "name": "木棉斋" }
      ]
    },
    {
      "client": "172.21.101.11",
      "name": "西丽校区",
      "buildings": [
        { "id": "01", "name": "梧桐树#" },
        /* ... */
      ]
    }
  ]
}
```

Built from `electrifyszu/data/buildings.txt` + `electrifyszu/data/apartment_buildings.txt`.

---

#### `GET /api/building-ranking`

Floor power-consumption leaderboard for a building.

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `client` | string | no | Campus client IP |
| `buildingId` | string | no | Building identifier |

**Success Response**

```json
{
  "ok": true,
  "data": {
    "client": "192.168.84.87",
    "building_id": "7126",
    "sampled": 39,
    "generated_at": "2026-05-22T10:00:00",
    "ranking": [
      { "room_name_masked": "7*", "total_used_kwh": 68.2, "rank": 1 },
      /* ... descending order */
    ]
  }
}
```

Room names are masked for privacy (first character preserved). Reads from pre-built cache file `data/ranking_cache.json`.

---

#### `GET /api/apartment/floors`

Floors for a given apartment building (丽湖).

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `building` | string | yes | Building code (e.g. `"01"`) |

**Errors:** `BUILDING_NOT_FOUND` (404) if unknown code.

---

#### `GET /api/apartment/rooms`

Rooms within a floor of an apartment building (丽湖).

**Parameters**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `building` | string | yes | Building code |
| `floor` | string | yes | Full floor code (e.g. `"0105"`) |

---

### Demo & Utilities

#### `GET /api/demo-status`

Returns hardcoded demo data requiring no campus network. Identical schema to `/api/status`.

**Parameters:** None.

---

#### `GET /api/version`

```json
{"ok": true, "version": "2.7182", "python": "3.12.4"}
```

---

#### `GET /api/health`

```json
{"ok": true, "status": "healthy", "version": "2.7182", "python": "3.12.4", "timestamp": "2026-05-25T10:00:00"}
```

Suitable for Docker HEALTHCHECK and uptime monitors.

---

#### `GET /api/github-stars`

Repo star count, refreshed at most once per hour.

```json
{"ok": true, "stars": 42}
```

Sources from `https://api.github.com/repos/jinqKing/ElectrifySZU`. Falls back to stale cache on failure.

---

### Subscription Management

#### `POST /api/subscriptions`

Register a low-balance alert subscription. Uses double opt-in: submission succeeds but remains inactive until the user confirms via email.

**Same-origin enforcement:** Browser POSTs require valid `Origin` or `Referer` header matching the request `Host`. Direct script calls without either header are accepted (assumed same-process).

**Body formats supported:** `application/json`, `multipart/form-data`, `application/x-www-form-urlencoded`. Max 64 KB.

**Input Fields**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | yes | Recipient email (@email.szu.edu.cn or @mails.szu.edu.cn by default) |
| `client` | string | no | Overrides campus client IP |
| `campusName` | string | no | Overrides campus name |
| `buildingId` | string | no | Overrides building ID |
| `buildingName` | string | no | Overrides building name |
| `roomName` | string | no | Overrides room number |
| `thresholdKwh` | number/string | no | Alert threshold in kWh (must be > 0, ≤ 10000) |
| `alertEnabled` | boolean | no | Low-balance warnings (default `true`) |
| `dailyReportEnabled` | boolean | no | Daily usage reports (default `false`) |

Omission of location fields causes fallback to `.env` defaults.

**Success Response** (201 Created)

```json
{
  "ok": true,
  "data": {
    "email": "student@email.szu.edu.cn",
    "campus_name": "深大新斋区",
    "building_name": "风槐斋",
    "room_name": "713",
    "threshold_kwh": 20,
    "alert_enabled": true,
    "daily_report_enabled": false,
    "verified": false
  },
  "message": "Verification email sent...",
  "verification_required": true
}
```

If the email was previously verified and activated, `verification_required` is `false` and the existing subscription is simply updated.

**Validation Rules**

- Email must match `[^@\s]+@[^@\s]+\.[^@\s]+` and be ≤ 254 characters.
- Email domain must be in `ALLOWED_EMAIL_DOMAINS` (comma-separated env var, default `@email.szu.edu.cn,@mails.szu.edu.cn`).
- Location fields reject control characters and enforce length caps.
- Deduplication key: `(email_lower, client, building_id, room_name)`.

See [Troubleshooting](./TROUBLESHOOTING.md) for common failures.

---

#### `GET /api/subscriptions/verify?token=TOKEN`

Activate a pending subscription. Responds with **302 Redirect** to `/?notice=verified&email=...&campus=...&building=...&room=...`.

Token generated by `secrets.token_urlsafe(24)`, compared via constant-time `secrets.compare_digest()`. Expires after 24 hours.

**Redirect notices:** `verified`, `already_verified`, `verify_expired`, `verify_invalid`.

---

#### `GET /api/unsubscribe?token=TOKEN`

Disable a subscription. Sets `enabled=false`; preserves `verified` flag. Responds with **302 Redirect**.

**Redirect notices:** `unsubscribed`, `already_unsubscribed`, `unsubscribe_invalid`.

---

#### `POST /api/alerts/check`

Manually trigger one alert-pass sweep. Requires authentication.

**Auth:** Header `X-Admin-Token` must match `ALERT_ADMIN_TOKEN` env var. Comparison via `hmac.compare_digest()` (constant-time).

**Body** (JSON recommended)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `skipRecent` | boolean | `true` | Skip subscriptions already alerted today |

**Success Response**

```json
{
  "ok": true,
  "data": {
    "checked": 12,
    "alerts_sent": 3,
    "reports_sent": 1,
    "skipped": 8,
    "failed": 0,
    "sent": 4
  }
}
```

Subscriptions grouped by `(client, campus_name, building_id, room_name)` so identical rooms share one API call.

In production mode, `_fetch_room_data()` first attempts a SQLite snapshot with extended TTL (48h — reliability over real-time). Falls through to live campus-API fetch only on cache miss.

---

### Community Interaction

#### `POST /api/like/init`

Issue a unique like identity. Called once per session.

**Success Response**

```json
{"ok": true, "id": "svr-a1b2c3d4e5f6g7h8"}
```

Format: `svr-` followed by 16 lowercase hex digits. Stored atomically in `data/likes.json`.

---

#### `POST /api/like`

Cast a vote. Accepts the ID returned by `/api/like/init`.

**Body**

```json
{"id": "svr-a1b2c3d4e5f6g7h8"}
```

Each ID can only successfully like once. Repeated attempts return `already_liked: true`.

**Success Response**

```json
{"ok": true, "already_liked": false, "count": 42, "users": 128}
```

Thread-safe via `threading.Lock`. Persists via atomic-write (NamedTemporaryFile → fsync → rename).

---

#### `GET /api/like/count`

Total like count without casting.

```json
{"ok": true, "count": 42}
```

---

#### `GET /api/like/my?userId=SVR_ID`

Check if a particular ID has already liked.

```json
{"ok": true, "data": {"liked": true}}
```

Validates userId against `^svr-[0-9a-f]{16}$`. Rejects invalid IDs with `INVALID_LIKE_ID`.

---

#### `GET /api/stats`

Aggregate community metrics.

```json
{"ok": true, "data": {"likes": 42, "users": 128}}
```

`likes` = votes cast, `users` = identities ever issued.

---

## Rate Limits

Backend applies no intrinsic rate limiting. All throttling relies on the reverse-proxy layer ([Nginx config](../deploy/nginx/electrifyszu.conf)):

| Zone | Paths | Rate | Burst |
|------|-------|------|-------|
| `electrifyszu_api` | `/api/status`, `/api/subscriptions` | 12/min | 8 / 5 |
| `electrifyszu_general` | other `/api/*` | 30/min | 15 |

Per-source-address, tracked via `$binary_remote_addr`. Behind CDN/proxy, configure `realip` directives accordingly.

## Request Size Limits

- Maximum POST body: **64 KB** (`MAX_REQUEST_BODY_BYTES` in `types.py`)
- Nginx `client_max_body_size`: **256 kB** (outer bound)

Exceeding limits returns `REQUEST_TOO_LARGE` (413).
