# ElectrifySZU Development Roadmap

Strategic milestones organized by priority band. Each phase depends on prior completion — skipping phases risks brittle foundations.

Last reviewed: 2026-05-27

---

## Current Snapshot

| Metric | Value |
|--------|-------|
| Backend LOC | ~5,800 |
| Frontend LOC | ~7,700 |
| Test count | 62 (all offline-safe) |
| Untested backend LOC | ~1,874 |
| Frontend tests | 0 |
| Documentation | 7 dedicated docs |
| CI pipelines | 2 (backend tests + GH Pages) |
| Deployment | Docker Compose (public + campus) |
| Active committers | Student team (Matrix) |
| Total commits | 160+ |

**Strengths:** well-architected split (frontend/API/campus), comprehensive docs, live-deployed, mature subscription flow, dual-environment deployment playbooks.

**Growing pains:** large untested zones (especially `apartment/`), no frontend automation, lightweight lint rules, ad-hoc release process, no observability layer.

---

## Phased Plan

### Phase 1 — Foundation *(Next Sprint)*

Close obvious quality gaps without altering production behaviour. Low-risk, high-leverage.

| Pri | Item | Description | Approach | Est. | Risk |
|-----|------|-------------|----------|------|------|
| P0 | Backfill backend coverage | Test 4 biggest blind spots: `apartment/api.py` (599 L), `server/middleware.py`, `server/handlers/{status,subscription}`, `server/router` | Standard pytest fixtures + mocked HTTP; reuse patterns from existing `test_server_security.py` | 4–6 h | 🟢 |
| P0 | Coverage gate in CI | Block merges when coverage dips below threshold | Add `pytest-cov` to `[dev]` extras; `--cov-fail-under=60` in `ci.yml` | 30 m | 🟢 |
| P1 | Lint hardening | Progressive ruf expansion | Dry-run `UP SIM ARG FLY PT` → batch-fix → activate; add `ruff format` | 2 h | 🟡 |
| P1 | Frontend ESLint | Basic JS quality checks | `.eslintrc` targeting `web/modules/` with browser-global awareness | 1 h | 🟢 |
| P1 | Frontend smoke tests | Automate critical UI flows | Vitest (vanilla-compatible); cover chart render, i18n swap, subscription form validation, likes debouncing | 4–8 h | 🟢 |

**Done signal:** CI enforces ≥ 60 % backend coverage, lint-clean on every push, three major frontend interactions covered by automated tests.

---

### Phase 2 — Reliability *(Following Month)*

Catch defects in production before students encounter them. Shift-left on operations.

| Pri | Item | Description | Approach | Est. | Risk |
|-----|------|-------------|----------|------|------|
| P0 | Concurrency stress tests | Validate thread-safety guarantees | Hammer `SubscriptionStore` under concurrent save/verify cycles; fire simultaneous `AlertRunner` sweeps | 3 h | 🔴 may expose genuine races |
| P0 | Structured-log export | Make prod logs machine-queryable | JSON-lines output via `RotatingFileHandler` + custom JSON formatter; rotation policy (7 days, 50 MB cap) | 2 h | 🟡 alters log format briefly |
| P1 | Backup automation | Guard against data-loss | Systemd timer or crontab: snapshot `data/*.db` + archive off-machine; 30-day retention window | 1 h | 🟢 |
| P1 | Deep health endpoint | Surface internal degradation | Extend `/api/health` to report disk free %, DB ping, SMTP TCP probe, uptime; degrade to 503 when unhealthy | 2 h | 🟢 |
| P1 | Dependency scanner | Flag vulnerable transitive deps | Enable Dependabot/Renovate for auto-update PRs; lock minimum semvers in `pyproject.toml` | 30 m | 🟢 |

**Done signal:** Scheduled backups running, dependabot opening PRs, health endpoint reflects subsystem vitality, concurrency edge-cases catalogued.

---

### Phase 3 — Scale *(Quarter End)*

Handle subscriber growth gracefully — higher traffic, longer uptimes, broader environments.

| Pri | Item | Description | Approach | Est. | Risk |
|-----|------|-------------|----------|------|------|
| P0 | Performance baselines | Publish measurable SLAs | Load-test `/api/status` & `/api/buildings` at 100 rpm; profile `AlertRunner` sweep at 500 subs; benchmark cold-start | 3 h | 🟡 may uncover capacity ceilings |
| P1 | Multi-Python CI matrix | Guarantee forwards-compat | `ubuntu-latest × [3.11, 3.12, 3.13]` in CI; flag `sys.version_info` gates | 1 h | 🟢 |
| P1 | Rate limiting | Shield against abuse | Sliding-window limiter (`limits` lib) on `/api/status` and `/api/subscriptions`; env-var tuned caps | 2 h | 🟡 adds rejection paths |
| P1 | Graceful shutdown | Zero-drop deploys | SIGTERM handler: refuse-new → drain-inflight → flush-pending-alerts → exit | 2 h | 🟢 |
| P2 | Geo redundancy | Survive regional outage | Secondary-region mirror; async DB replication (WAL-mode + scheduled rsync) | 4–8 h | 🔴 infra commitment |

**Done signal:** Throughput benchmarks published, rate-limits enforcing, rolling redeployments safe without dropping active queries.

---

### Phase 4 — Polish *(Ongoing Cadence)*

Professional-grade packaging and deterministic releases. Minimise human toil.

| Pri | Item | Description | Approach | Est. | Risk |
|-----|------|-------------|----------|------|------|
| P0 | Semantic-release automation | Derive changelog + version from commits | Conventional-commit parser → auto-bump → draft GitHub Release → PyPI publish (eventual) | 2 h | 🟡 needs commit-discipline |
| P1 | Artifact publishing | Distributable wheels | `build-system.requires` → hatchling/wheel; upload to private registry or PyPI | 1 h | 🟢 |
| P1 | Signed Docker images | Tamper-proof containers | sha256 digests; `latest` + semver tags; cosign attestation | 1 h | 🟢 |
| P2 | Accessibility audit | WCAG 2.2 AA compliance | Pa11y/axe-core sweep against deployed site; fix contrast, keyboard nav, screen-reader landmarks | 3–5 h | 🟡 visual adjustments |
| P2 | Privacy-friendly analytics | Opt-out telemetry | Self-host Plausible/Growthpress; honour `DNT`; scrub identifying UTMs | 2 h | 🟢 |

**Done signal:** Master-push auto-generates tagged releases with changelogs; immutable signed artefacts pushed to registries.

---

## Cross-Cutting Practices *(Adopt Immediately)*

Not phase-gated — integrate now:

1. **Conventional Commits** — Enforce `feat|fix|refactor|test|docs|perf|ci:` prefix via `.husky/commit-msg` hook (or pre-commit YAML equivalent).
2. **PR Checklist** — Ship `.github/PULL_REQUEST_TEMPLATE.md` listing: linked issue, screenshot delta (UX), test proof, backwards-compatability statement.
3. **Tech-debt quota** — Cap ≤ 20 % of each sprint on backlog reduction (deprecated aliases, renamed fields, orphaned comments).
4. **Blameless post-mortems** — Lightweight incident retrospectives filed under `docs/incidents/YYYY-MM-DD-name.md`; trigger when production disruption exceeds 30 minutes.

---

## Recommended Ramp-Up Sequence

Small-team reality forces ruthless prioritisation:

```
Week 1  P0 foundation only
        ├─ backfill apartment + middleware tests  (~5 h)
        ├─ pytest-cov gate wired into CI          (~0.5 h)
        └─ ruff dry-run + batch-fix               (~2 h)

Week 2  P1 foundation + P0 reliability
        ├─ frontend vitest smoke tests            (~4 h)
        ├─ concurrency stress tests               (~3 h)
        └─ backup cron + deep-health              (~2 h)

Week 3+ Stabilise — triage anything Week 1-2 surfaced
          (race conditions, flakes, capacity alarms)
```

Postpone Phase 3–4 until active-subscriber count surpasses ~200 or the team gains spare bandwidth. At that inflection point, performance and release engineering naturally rise to urgent concern.

---

## Appendix: Decision Criteria

| Question | Criterion | Owner |
|----------|-----------|-------|
| Is a change worth merging? | Passes CI + covers affected code + reviewer LGTM | Maintainer |
| Has a milestone shipped? | Done-signalled criteria met + CHANGELOG updated | Lead |
| Is a feature deferred? | Subscriber demand < 200 or no volunteer champion | Group vote |
| Is downtime acceptable? | Only during maintenance windows announced ≥ 24 h advance | Ops lead |
