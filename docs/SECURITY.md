# Security Architecture

Overview of implemented defenses, their rationale, attack surfaces, and acknowledged limitations.

## Threat Model

ElectrifySZU operates as a semi-public service bridging the campus intranet and the wider internet. Primary concerns:

1. **Unauthorized access** to campus power-management infrastructure (billing manipulation, enumeration)
2. **Abuse of email system** (spam relaying, credential harvesting)
3. **Data leakage** of personal identifiers (emails, room assignments)
4. **Denial-of-service** amplification against the campus API

Trust assumptions:
- The campus API is trusted (we accept its data verbatim).
- Students may act adversarially towards each other.
- Administrators operate in good faith but deserve audit trails.

---

## Implemented Defenses

### 1. Same-Origin Enforcement (XSRF Protection)

**Problem:** Malicious sites could trick logged-in browsers into issuing POST requests (creating subscriptions, liking, triggering alerts).

**Implementation:** `validate_same_origin()` in `middleware.py` intercepts every POST request before routing.

Logic:
```
1. Extract Host header → normalize to lower-case
2. Allowed origins = { http://host , https://host }
3. Check Origin header ∈ allowed origins → PASS
4. Else check Referer netloc ∈ allowed origins → PASS
5. Else REJECT with FORBIDDEN_ORIGIN (403)
6. Neither header present → PASS (assumes same-process/script caller)
```

**Coverage:** All five POST endpoints (`/api/subscriptions`, `/api/alerts/check`, `/api/like/init`, `/api/like`, and any unmapped POST).

**Limitation:** Case-sensitive `Host` normalization mitigated by lowering. Does not protect GET endpoints (but those are side-effect-free by design). Step 6 allows direct programmatic clients without cookie jars — acceptable since subscription creation requires email verification anyway.

---

### 2. Admin Token Authentication

**Problem:** `POST /api/alerts/check` and the 3 archive admin endpoints (`POST /api/archive/batch`, `GET /api/archive/status`, `GET /api/archive/history`) trigger expensive campus-API fan-outs or expose internal data. Exposing them publicly enables denial-of-service and data-leakage attacks.

**Implementation:** Two enforcement layers:

1. **`middleware.validate_admin_token()`** — Constant-time HMAC comparison via `hmac.compare_digest()`.
   ```python
   expected = os.getenv("ALERT_ADMIN_TOKEN", "").strip()
   supplied = handler.headers.get("X-Admin-Token", "").strip()
   return bool(expected and supplied and hmac.compare_digest(supplied, expected))
   ```
2. **`_require_auth()` guard in `handlers/archive.py`** — Wraps every archive endpoint. Returns `ADMIN_AUTH_REQUIRED` (401) on failure.

```python
expected = os.getenv("ALERT_ADMIN_TOKEN", "").strip()
supplied = handler.headers.get("X-Admin-Token", "").strip()
return bool(expected and supplied and hmac.compare_digest(supplied, expected))
```

Both sides must be non-empty. Timing-attack resistant.

**Operational requirement:** Generate strong secret: `python -c "import secrets;print(secrets.token_hex(16))"` → paste into `.env`.

---

### 3. Like Identity Signing Scheme

**Problem:** Unlimited voting would trivially inflate engagement metrics. Login-based auth adds friction unacceptable for a casual "thumbs-up".

**Solution:** Two-phase issuance + spend model.

Phase 1 — Issuance (`POST /api/like/init`):
- Server generates UUID-based ID: `svr-{16-hex-chars}`
- Appends to `seenIds[]` array (proves server originated it)
- Persisted atomically

Phase 2 — Spend (`POST /api/like`):
- Validates format against `^svr-[0-9a-f]{16}$`
- Checks ID exists in `seenIds[]` (rejects forged IDs)
- Checks ID NOT in `likedIds[]` (one-use consumable)
- Moves ID from eligible → consumed

**Why forgery-resistant:** The 128-bit entropy makes brute-force guessing astronomically impractical. Even observing many valid IDs reveals nothing reusable (UUID v4 randomness).

**Persistence safety:** Atomic write (see Section 5) prevents data loss on crash mid-update.

---

### 4. Input Sanitization Layer

Applied uniformly in `types.read_request_data()` and `store.build_subscription()`.

| Control | Implementation | Effect |
|---------|----------------|--------|
| Body size cap | `MAX_REQUEST_BODY_BYTES = 64×1024` | Blocks memory exhaustion from oversized payloads |
| Content-Type gating | Explicit enum check | Rejects unexpected media types (returns 415) |
| JSON structural check | `isinstance(payload, dict)` | Prevents array injection into keyed parsers |
| Value stripping | `_clean_request_value()` trims whitespace | Eliminates leading/trailing space exploits |
| Control char filter | Regex `[\x00-\x1f\x7f]` on subscription fields | Blocks null-byte injection, CR/LF smuggling |
| Length caps | Per-field maximums (table below) | Bounds downstream buffer sizes |

Field length limits:

| Field | Max Characters |
|-------|---------------|
| `email` | 254 (RFC 5321 compliant) |
| `client` | 64 |
| `building_id` | 32 |
| `campus_name` | 80 |
| `building_name` | 80 |
| `room_name` | 32 |
| `threshold_kwh` | numeric, range (0, 10000] |

Email additionally validated against RFC-style regex and configurable domain whitelist.

---

### 5. Atomic Write Semantics

**Problem:** Crash during file write leaves corrupt data, losing persistent state (lost likes, orphaned subscriptions).

**Pattern used identically for both `data/likes.json` and `data/subscriptions.csv`:**

```
1. Open NamedTemporaryFile in SAME directory (ensures same filesystem)
2. Write complete new content
3. file.flush(); os.fsync(fileno)  → durability guarantee
4. close file
5. os.rename(temp, target)          → POSIX atomic swap
6. On ANY failure before step 5: unlink temp file, propagate exception
```

Guarantees: readers always see either the previous complete file OR the new complete file. Never a torn intermediate state.

**Prerequisite:** Temp and target must reside on the same device (cross-device rename is not atomic). Achieved by specifying `dir=target_parent` in `NamedTemporaryFile`.

---

### 6. Thread-Safe State Access

Two mutable datastores protected by locks:

| Resource | Lock | Granularity |
|----------|------|-------------|
| `data/likes.json` | `_likes_lock` (global `threading.Lock`) | Coarse-grained around individual CRUD ops |
| `data/subscriptions.csv` | `_store_lock(path)` (singleton `Lock` per file path) | Fine-grained per-store-instance |

The per-path lock factory (`_store_lock`) shares a single `Lock` instance among all `SubscriptionStore` objects targeting the same file, preventing race conditions even when multiple handler invocations concurrently access the same CSV.

Shutdown coordination uses `threading.Event` (`_shutdown_event`) for graceful alert-worker termination.

---

### 7. Access Log Redaction

**Purpose:** Prevent accidental exposure of sensitive identifiers (tokens, emails) in log aggregation, incident reviews, or support tickets.

**Mechanism:** `redact_access_log()` parses the HTTP request line, identifies query parameters whose keys belong to `SENSITIVE_QUERY_KEYS = {"token", "email", "userId", "id"}`, and replaces their values with `***`.

Example transformation:
```
Before:  GET /api/subscriptions/verify?token=abc123xyz&notice=verified
After:   GET /api/subscriptions/verify?token=***&notice=verified
```

Also applied to `log_message()` output, meaning both file and console logs are sanitized.

---

### 8. Static File Path Traversal Prevention

**Risk:** Crafted URL paths containing `..` segments escaping the `web/` directory.

**Defense:** `serve_static()` in `static.py` performs canonical resolution containment check:

```python
target = (base_dir / path.lstrip("/")).resolve()
target.relative_to(base_dir)   # raises ValueError if escaped
```

Any path resolving outside `web/` returns 404 rather than leaking sibling files.

---

### 10. SQLite Database Access Control

**Risk:** `data/electrifyszu.db` is a single binary file containing all subscriptions, room snapshots, daily consumption records, and cached room mappings. If an attacker gains filesystem access, they can exfiltrate the entire dataset without API calls.

**Mitigation:** 
- File permissions should restrict read access to the server process user only (`chmod 600` / `chown`).
- `ELECTRIFYSZU_DB_PATH` env var allows pointing to a protected volume in container deployments.
- No encryption-at-rest is implemented; a dedicated secrets volume is recommended for production.
- Legacy CSV/JSON files (`data/subscriptions.csv`, `data/likes.json`) are superseded by SQLite but retained until migration is verified — treat them with equivalent sensitivity.

---

### 11. Email Domain Whitelist

**Purpose:** Restrict subscription recipients to institutional accounts, reducing spam-relay abuse risk.

Default: `@email.szu.edu.cn` and `@mails.szu.edu.cn`. Configurable via `ALLOWED_EMAIL_DOMAINS`.

Enforced at subscription creation time in `store.build_subscription()`. Changes to the whitelist apply prospectively only (existing subscriptions retain validity).

---

## Defense-In-Depth Stack

How the layers combine for typical attack vectors:

```
Attacker → Nginx rate-limit → XSRF origin check → Body size/type gate
         → Input sanitization → Business-logic validation
         → Atomic persistency → Audit logging (redacted)
         
External view:                                                    Internal trust boundary:
[Internet] → [Nginx] → [server.py middleware] → [handler logic] → [storage]
                                                      ↑
                                              [Campus API ◂◂ trusted upstream]
```

---

## Known Limitations & Mitigation Plans

| Gap | Risk Level | Planned Remediation |
|-----|------------|---------------------|
| No CAPTCHA on subscription form | Low-Medium | Bot volume currently manageable; add turnstile/hcaptcha if spam increases |
| Rate limiting delegated to Nginx | Medium | Works fine with proper Nginx config; bare-server deployments lack protection — document prominently |
| No audit trail for admin operations | Low | Consider appending admin-action log entries (who triggered `/api/alerts/check`, `/api/archive/batch`) |
| Tokens stored plaintext in SQLite | Low-Medium | Acceptable for short-lived tokens (< 24h expiry); hash+salt for long-term retention |
| No CSRF token for admin endpoints | Low | `X-Admin-Token` serves equivalent purpose for machine clients; human-admin UI TBD |
| Passwords visible in process env | Standard cloud risk | Rotate regularly; consider encrypted vault for production |
| No automated dependency scanning | Low | Add Dependabot/Renovatebot for CVE awareness |
| SQLite database not encrypted at rest | Medium | For production with sensitive data, mount on encrypted volume or add sqlcipher layer |
| IPv4-only rate limiting | Low | `$binary_remote_addr` loses accuracy behind NAT; upgrade to `$http_x_real_ip` with `realip` module |

---

## Compliance Notes

- **GDPR relevance:** Minimal. Stores email + room assignment (potentially personally identifiable). Provide deletion mechanism upon request via admin contact.
- **Chinese PIPL:** Similar considerations. Student emails constitute personal information. Retention limited to active subscription lifetime.
- **Log retention:** Rolling files capped at 5 copies × 10 MiB ≈ 50 MiB total. Logs older than capacity are discarded automatically.
