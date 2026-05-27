# Troubleshooting

Diagnose problems symptom-first. Find your issue in the table below, jump to the solution.

## Quick Diagnostic Commands

| Goal | Command |
|------|---------|
| Verify campus network reachability | `ping 192.168.84.3` or `curl -v "$DORM_API_BASE/selectList.do?type=3&..."` |
| Verify SMTP works | `uv run electrifyszu-delivery-test --to you@email.szu.edu.cn --subject "Test" --content "Hello"` |
| View latest logs | `tail -50 logs/electrifyszu.log` |
| Manual alert sweep | `curl -X POST http://127.0.0.1:8000/api/alerts/check -HX-Admin-Token:$ALERT_ADMIN_TOKEN -d '{"skipRecent":false}'` |
| Inspect subscription DB | `cat data/subscriptions.csv \| column -t -s','` |
| Check likes store integrity | `python -c "import json; print(json.dumps(json.load(open('data/likes.json')), indent=2)[:500])"` |
| Discover roomId | `uv run python -m electrifyszu.dorm.discover "<paste_selectList_URL>"` |
| Archive status | `uv run python -m electrifyszu.archive.cli status` |
| List cached room mappings | `uv run python -m electrifyszu.archive.cli mappings --show` |
| Collect one room manually | `uv run python -m electrifyszu.archive.cli collect --building 7126 --room 713` |
| Batch collect overdue tasks | `uv run python -m electrifyszu.archive.cli batch` |
| View stored history for a room | `uv run python -m electrifyszu.archive.cli history --building 7126 --room 713` |
| Restart server gracefully | Ctrl+\`C\` (drains in-flight requests, shuts down alert worker) |

---

## Problem Index

### Query Errors

#### `ROOM_NOT_FOUND` — Room not discovered

**Root cause:** `discover_room_id()` could not find a matching `roomId` for the given `(building_id, room_name, client)` triple.

Common reasons:

1. **Typo in room number.** `"713"` ≠ `"713 "` (trailing space matters). Ensure `roomName` matches the official designation.
2. **Wrong campus/client selected.** Each campus has a distinct `client` IP. Selecting "粤海" while querying a "新斋区" room fails silently because the underlying systems differ.
3. **Building ID mismatch.** The `buildingId` embedded in the campus selector must correspond to the correct `client`. Check `electrifyszu/data/buildings.txt` for authoritative mappings.
4. **Newly assigned room.** Rooms provisioned after the last crawl won't appear. Open the campus system manually to confirm the room appears in the dropdown.

**Fix:** 
- Click "载入演示" to verify the frontend works independently.
- Paste the `selectList.do` URL from the campus website into `python -m electrifyszu.dorm.discover` to extract the real `roomId`.
- Contact admins if the room genuinely does not exist in the campus system.

---

#### `CAMPUS_NETWORK_ERROR` — Cannot reach campus API

**Root cause:** Network unreachable, DNS failure, connection refused, or SSL handshake error contacting `DORM_API_BASE`.

Diagnosis:

```bash
# From the server machine:
curl -v http://192.168.84.3:9090/cgcSims/
# Expected: HTTP 200 or HTML login page
# Failure indicators: "Connection refused", "Network is unreachable", timeout
```

Common fixes:

| Situation | Fix |
|-----------|-----|
| Server outside campus network | Deploy a relay node on campus, forward `DORM_API_BASE` to localhost via SSH tunnel or frp |
| Wrong `DORM_API_BASE` | Edit `.env`, verify URL resolves |
| Proxy interference | Set `HTTP_PROXY=""` in `.env` when direct routing works (avoid proxy for intranet addresses) |
| Intermittent outage | Retry; campus systems occasionally go down for maintenance |

---

### Subscription Issues

#### Verification email never arrives

Check in priority order:

1. **Spam folder** — Plain-text emails from unfamiliar domains land there frequently.
2. **SMTP placeholders not replaced** — If `.env` still contains `smtp.example.com` or `your_email_authorization_code`, `EmailConfig.from_env()` raises `RuntimeError("placeholder")`. This prevents ALL outgoing mail.
3. **Domain whitelist blocks recipient** — By default only `@email.szu.edu.cn` and `@mails.szu.edu.cn` are accepted. Override via `ALLOWED_EMAIL_DOMAINS=comma,sep,domain,list` in `.env`.
4. **SMTP credentials wrong** — Look for `SMTP认证失败` in `logs/electrifyszu.log`. Regenerate authorization code if using QQ/NetEase Gmail.
5. **Rate limited by provider** — Free SMTP tiers throttle bulk sends. Wait and retry.

Debug:

```bash
# Dry-run SMTP test (creates temp subscription, skips campus API):
uv run electrifyszu-delivery-test --to you@email.szu.edu.cn --show-config
```

---

#### Subscription stuck in "pending" forever

After clicking the verify link, the notice says `verify_expired` or `verify_invalid`.

| Cause | Fix |
|-------|-----|
| Link clicked after 24 h | Expired token cleared; resubmit the subscription form to receive fresh link |
| Token tampered/copied incorrectly | Copy the FULL URL from the email, not partial |
| Multiple submissions overlapped | Later submission generates NEW token, invalidating earlier one; use latest link |

---

#### Alerts fire despite sufficient balance

Likely causes:

1. **Threshold lowered recently.** The stored threshold persists across updates. Check `data/subscriptions.csv` column `threshold_kwh` for the affected row.
2. **Stale polling data.** If the campus API reported outdated readings, the snapshot may lag reality. Force-refresh via `POST /api/alerts/check`.
3. **`ALERT_MODE=testing` with `FORCE_SEND_ALERT=1`.** Testing mode fabricates data intentionally. Reset both flags.

---

#### Alerts don't fire when balance IS low

Check:

1. **Subscription not verified?** Only `enabled AND verified` subscriptions enter the alert pool. Check `data/subscriptions.csv` columns `enabled` and `verified`.
2. **Already alerted today?** Each subscription fires at most once per calendar day (`last_alert_date` gate). To override temporarily: `POST /api/alerts/check` with `{"skipRecent": false}`.
3. **`alert_enabled` turned off?** Some subscribers opt-out of alerts but keep daily reports. Column `alert_enabled` must be `true`.
4. **Alert worker crashed?** Check logs for exceptions in `[alerts]` namespace. Restart server.
5. **Timing hasn't arrived.** Default `ALERT_CHECK_TIME=08:00`. Change in `.env` and restart.

---

### Frontend Problems

#### Blank white page on load

1. Check browser DevTools Console for JS errors. Most commonly caused by:
   - Chart.js failing to load (CDN unavailable) — switch to bundled fallback
   - Incorrect `BASE_URL` pointing to nonexistent backend
2. Try `http://127.0.0.1:8000` directly (bypasses any proxy misconfiguration).
3. Hard refresh (`Shift+F5` / Cmd+Shift+R) clears stale service worker caches.

---

#### Loading spinner doesn't replay on second query

Ensure `resetLoadingAnimation()` is called before initiating the next fetch. The animation DOM nodes are reused, not recreated. Check `web/modules/loading-status.js`.

---

#### Building dropdown empty or incorrect

Dropdown populated from `GET /api/buildings`. Empty means:
- `electrifyszu/data/buildings.txt` is missing or malformed
- `electrifyszu/data/apartment_buildings.txt` is missing or malformed

Regenerate: `python -m electrifyszu.apartment.cli buildings --online` (requires campus network).

---

### Deployment Failures

#### Docker container exits immediately

```bash
docker logs electrifyszu
```

Look for:
- `ModuleNotFoundError` → Image built without copying source properly (check `Dockerfile COPY . .`)
- Permission denied on `/app/data` → Volume mount ownership mismatch; run `chown -R 1000:1000 ./data`
- `.env` not loaded → Mount explicitly: `volumes: [- $(pwd)/.env:/app/.env]`

---

#### Nginx returns 502 Bad Gateway

Upstream `127.0.0.1:8000` is unreachable:
- Container uses `network_mode: host` — ensures port alignment. Without it, bind to `0.0.0.0:8000` and adjust upstream.
- Process died — check `journalctl -u docker` or `ps aux | grep server.py`.

---

#### Mixed-content warning (HTTPS site loads HTTP resources)

Deploy behind HTTPS-aware proxy setting `X-Forwarded-Proto: https`. The server honors this header to construct correct callback URLs (verification links, unsubscribe links). Also set `PUBLIC_BASE_URL=https://your.domain.com`.

---

### Archive / Cache Issues

#### `/api/status` always returns `_source:"live"` (cache never hit)

The cache TTL is 24 hours. If you keep seeing cache misses:

1. **Fresh database.** First-run or new DB has no snapshots. After one live fetch, subsequent requests hit cache.
2. **Different room each time.** Cache is per-room; querying 20 different rooms needs 20 first-time fetches.
3. **Server restarted after < 24h.** This is fine — cache persists across restarts (SQLite on disk).

Check cache state:
```bash
uv run python -m electrifyszu.archive.cli status
# Look at room_snapshots count and oldest/newest timestamps
```

#### Archive batch collection silently skips rooms

Tasks with >5 consecutive failures are auto-disabled. Check:
```bash
uv run sqlite3 data/electrifyszu.db "SELECT building_id, room_name, last_status, consecutive_failures FROM collection_tasks WHERE enabled=0"
```
Re-enable a disabled task:
```bash
uv run sqlite3 data/electrifyszu.db "UPDATE collection_tasks SET enabled=1, consecutive_failures=0 WHERE id=ID"
```

#### Room mapping cache returns stale internal_id

Mappings expire after 30 days by default. Force refresh by collecting the room, or purge expired:
```bash
uv run python -m electrifyszu.archive.cli mappings --purge
```

#### SQLite database file location

The archive database lives at `data/electrifyszu.db` by default. Override via `ELECTRIFYSZU_DB_PATH` environment variable.

---

### Data Corruption Recovery

#### `data/likes.json` corrupted

Atomic writes prevent mid-operation corruption. But filesystem crashes can leave a bad file. Safe recovery:

```bash
mv data/likes.json data/likes.json.corrupted.$(date +%s)
echo '{"count":0,"likedIds":[],"seenIds":[],"totalIssued":0}' > data/likes.json
```

Next boot repopulates counts from activity. Historical precision lost but functionality restored.

---

#### `data/subscriptions.csv` inconsistent

Recovery depends on damage extent:

| Damage | Action |
|--------|--------|
| Truncated tail | Restore from git: `git checkout HEAD -- data/subscriptions.csv` |
| Encoding garbled | Re-read with `encoding='utf-8-sig'` (handles BOM); store handles this transparently |
| Duplicate rows | Not possible (atomic write replaces entire file); indicates concurrent writers — impossible due to per-path locking |

Prevention: Never edit CSV manually. Use API endpoints exclusively.

---

### Logging Deep Dive

Logs written to `logs/electrifyszu.log` with rotating backups (`electrifyszu.log.1`, `.2`, …).

Configure via `.env`:

```ini
LOG_LEVEL=DEBUG          # Capture verbose traces
LOG_DIR=/var/log/my-app  # Alternate location
LOG_MAX_BYTES=52428800   # 50 MB rollover
LOG_BACKUP_COUNT=10      # Keep 10 generations
```

Console output includes colors: `server`=cyan, `email`=magenta, `alerts`=orange. File output strips colors.

Access-log lines contain timing: `127.0.0.1 - GET /api/status → 200 (45ms)`. Slow requests (>500ms) stand out visually.

Sensitive query parameters (`token`, `email`, `userId`, `id`) are redacted in access logs.
