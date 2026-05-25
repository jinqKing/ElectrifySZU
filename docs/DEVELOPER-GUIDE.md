# Developer Guide

Workflow standards, testing practices, branching discipline, and tips for productive contributions.

## Getting Started

### Prerequisites

- **Python 3.11+** (tested on 3.11–3.14)
- **[uv](https://docs.astral.sh/uv/)** package manager
- **Git** with worktree support (2.5+, practically universal now)

### Initial Setup

```bash
git clone https://github.com/jinqKing/ElectrifySZU.git
cd ElectrifySZU

# Sync dependencies (includes dev extras for testing)
uv sync --extra dev

# Prepare environment
cp .env.example .env
# Edit .env — fill in at least DORM_* and SMTP_* values

# Sanity check
uv run pytest -q          # Should pass (offline mocks)
uv run electrifyszu       # Starts HTTP server on :8000
```

Open `http://127.0.0.1:8000`. Click "载入演示" to explore without campus network.

### Hot Reload Note

The stdlib `ThreadingHTTPServer` supports **zero** hot reloading. Every code change requires restarting the process:

```bash
# Option 1: Simple restart
uv run server.py --port 8000

# Option 2: Auto-reload via watchdog (install optionally)
pip install watchdog
uv run python -m watchdog.server.server.py --port 8000

# Option 3: Just use Ctrl+C → rerun (fastest for small projects)
```

---

## Running Tests

### Quick Execution

```bash
uv run pytest -v           # Full output with passing test names
uv run pytest -q           # Compact summary (used by CI)
uv run pytest tests/foo.py # Specific file
uv run pytest -k "keyword" # Filter by test name substring
```

### Coverage Report

```bash
uv run pytest --cov=electrifyszu --cov-report=term-missing
```

### Writing New Tests

Template for a handler test:

```python
# tests/test_something_new.py
from __future__ import annotations

import io
import json
from unittest.mock import patch

from electrifyszu.server.handlers.types import send_json


def test_example():
    """Describe the invariant being tested."""
    # Arrange
    handler = FakeHandler(method="GET", path="/api/example?key=value")
    
    # Act
    handle_example(handler, {"key": ["value"]})
    
    # Assert
    assert handler.status_code == 200
    body = json.loads(handler.output.getvalue())
    assert body["ok"] is True
```

Template for a store/service test:

```python
def test_store_operation(temp_csv_path: Path):
    """Use the provided fixture for isolated CSV."""
    store = SubscriptionStore(temp_csv_path)
    result = store.save({...}, default_threshold=20.0)
    assert result.status == "pending_verification"
```

### Fixture Reference

| Fixture | Provides | Defined In |
|---------|----------|------------|
| `temp_csv_path` | Isolated CSV file path backed by `tmp_path` | `tests/conftest.py` |
| `tmp_path` | Temporary directory (pytest builtin) | pytest |

Legacy wrapper directories (`room-power-monitor/`, `apartment-power-monitor/`) have been consolidated into `electrifyszu/`. All imports should use the `electrifyszu.` qualified path directly.

### CI Pipeline

Tests run automatically on every PR and push to `master` via GitHub Actions:

```yaml
trigger: pull_request, push(master), workflow_dispatch
stack: ubuntu-latest → Python 3.11 → uv sync --extra dev --locked → pytest -q
env: Dummy credentials for DORM_*, SMTP_* (prevent real network calls)
```

View results at: **Actions → CI** tab. Green ✓ required before merge.

---

## Branch Strategy

### Norms

```
master          — Stable release branch. Always passes CI. Tags marked here.
feature/*       — Short-lived feature/experiment branches. Delete after merge.
bugfix/*        — Targeted repairs. Squash-merge into master.
```

### Worktree Workflow (Recommended for Parallel Features)

Worktrees enable developing multiple features simultaneously from a single checkout:

```bash
# Create a feature worktree
git worktree add ../ElectrifySZU-feat-x feat-x

# Each worktree gets its own working directory sharing the same .git/
# Modify freely without detaching from master

# List all worktrees
git worktree list

# Remove completed worktree
rm -rf ../ElectrifySZU-feat-x
git worktree prune
git branch -d feat-x
```

### Port Selection Rule (Multiple Instances)

Running servers from different worktrees requires distinct ports to avoid conflicts:

```bash
# Worktree A (master baseline)
uv run server.py --port 8000

# Worktree B (feat-alerts)
uv run server.py --port 8001

# Worktree C (feat-apartment)
uv run server.py --port 8002
```

Always specify `--port` when launching from a non-master worktree. Record chosen ports in your scratchpad.

### Checking Unmerged Worktrees

```bash
# From master worktree:
for wt in $(git worktree list | awk '{print $1}'); do
    branch=$(cd "$wt" && git rev-parse --abbrev-ref HEAD)
    ahead=$(git rev-list --count master.."$(cd "$wt" && git rev-parse HEAD)")
    if [ "$ahead" -gt 0 ]; then
        echo "  $branch ($wt): $ahead commits ahead of master"
    fi
done
```

---

## Commit Discipline

### Frequency

Commit after completing each logically coherent unit. Typical cadence:

```
Implement feature X     → commit
Add tests for X         → commit
Refactor extracted util → commit
Polish edge case        → commit
```

Avoid accumulating dozens of unrelated changes into mega-commits.

### Message Convention

```
Verb noun: brief scope descriptor

Longer explanation spanning the WHY (not WHAT—the diff shows THAT).
Reference ticket/discussion if applicable.
```

Good examples:
- `fix typo in email verification subject template`
- `add same-origin check for all POST endpoints`
- `make likes.json writes atomic via temp-file-rename`

Bad examples:
- `update stuff`
- `fix fix fix`
- `asdf`

### Changelog Updates

After significant additions or breaking changes, append to `CHANGELOG.md`:

```markdown
## [VERSION] - YYYY-MM-DD

### Added/Fixed/Changed/Security
- Bullet describing the change in user-visible terms.
```

Categories: `Added`, `Changed`, `Fixed`, `Removed`, `Security`. Follow [Keep a Changelog](https://keepachangelog.com/) spirit.

### Version Bumping

Version stored in `pyproject.toml` → propagated via `electrifyszu/version.py`:

```toml
[project]
version = "2.7182"    # Increment the rightmost digit
```

Convention: Euler-number-inspired sequence converging toward *e* (= 2.71828…). Patch bumps advance the last decimal position. Minor releases justify a CHANGELOG highlight section.

---

## Multi-Agent Collaboration Patterns

When coordinating with AI assistants (Codex, Copilot, Claude, etc.), use these proven techniques:

### Scoped Assignment Pattern

Assign discrete file scopes to parallel agents, with explicit exclusion zones:

```
Worker A: Implement X. WRITE SCOPE: foo/a.py, tests/test_a.py. DO NOT TOUCH: web/, bar/.
Worker B: Implement Y. WRITE SCOPE: bar/b.py, tests/test_b.py. DO NOT TOUCH: web/, foo/.
```

Negative constraints ("DO NOT MODIFY…") prevent conflicting edits.

### Progressive Disclosure Pattern

Don't dump everything at once. Sequence the conversation:

```
Step 1: Analyze current state, propose plan. DON'T modify files.
Step 2: I approve the plan. Now implement Phase A.
Step 3: Good. Continue with Phase B.
Step 4: Done. Please add tests for the new code.
```

### Post-Task Reporting Template

Ask each worker to conclude with:

```
Summary of changes:
Files modified: [...]
Files created: [...]
Tests added: [...]/[...] passed
Breaking changes: Yes/No
Needs manual QA: Yes/No
```

Comprehensive prompt archive: see `docs/prompts-collection.md`.

---

## Code Style Guidelines

### Python

- **Type hints** on all public interfaces (signatures + return types)
- **Docstrings** on all public functions/classes (Google or NumPy style)
- **Imports**: standard lib → third-party → local, separated by blank lines
- **String quotes**: single `'` for literals, double `"""` for docstrings
- **Max line width**: reasonable judgment (aim ≤ 100, tolerate longer for URLs/docstrings)
- **No wildcard imports** except in thin-wrapper compat shims (marked `# noqa: F401,F403`)

### JavaScript

- **Modules**: ES module syntax (`import/export`), no globals except intentional window exports
- **Naming**: camelCase for variables/functions, PascalCase for constructors/components
- **Strings**: backtick `` `template literals`` for interpolation, single `'quotes'` otherwise
- **Async**: `async/await` preferred over Promise chaining

### Markdown

- Headers use ATX style (`#`, `##`, ...)
- Tables aligned with pipes
- Code fences tagged with language identifier
- Relative links for intra-project references (`./API_REFERENCE.md`)

---

## Debugging Tips

### Enable Verbose Logging

```ini
# .env
LOG_LEVEL=DEBUG
```

Shows SQL-equivalent trace for CSV reads, SMTP handshakes, and HTTP request/response bodies.

### Interactive REPL Against Running Server

```python
# Terminal 1: uv run server.py --port 8000
# Terminal 2:
python
>>> import urllib.request, json
>>> r = urllib.request.urlopen("http://127.0.0.1:8000/api/health")
>>> json.loads(r.read())
{'ok': True, 'status': 'healthy', ...}
```

### Inspecting Subscription Database

```python
python
>>> from electrifyszu.subscription.store import SubscriptionStore
>>> store = SubscriptionStore("data/subscriptions.csv")
>>> for sub in store.list_all():
...     print(f"{sub.email:30s} {'ACTIVE' if sub.is_active else 'PENDING':8s} thresh={sub.threshold_kwh}")
```

### Reproducing Email Templates Locally

```python
python
>>> from electrifyszu.subscription.store import Subscription
>>> from electrifyszu.subscription.email_templates import alert_content
>>> # Construct a dummy subscription for preview
>>> sub = Subscription(email="test@test.com", client="192.168.84.87",
...     campus_name="粤海", building_id="7126", building_name="风槐斋",
...     room_name="713", threshold_kwh=20, alert_enabled=True,
...     daily_report_enabled=False, enabled=True, verified=True,
...     created_at="", updated_at="", verified_at="",
...     verification_token="", verification_token_expires_at="",
...     verification_sent_at="", last_alert_date="",
...     last_daily_report_date="", unsubscribe_token="abc123")
>>> print(alert_content(sub, {"remaining": 15, "room_name": "713", "status": "low", "last_record": "today"}, "http://127.0.0.1:8000"))
```

---

## Pull Request Checklist

Before requesting review, confirm:

- [ ] `uv run pytest -q` passes cleanly
- [ ] No debug prints left in code (`print(...)`, `pprint(...)`)
- [ ] New env variables documented in `docs/CONFIGURATION.md`
- `CHANGELOG.md` updated if user-facing change
- [ ] No modifications to `web/work-intro.*` unless intended
- [ ] Import paths use `electrifyszu.` qualification (not legacy `src.`)
- [ ] Diff reviewed for accidentally committed secrets/credentials

---

## Glossary

| Term | Definition |
|------|-----------|
| **Client** | IP address identifying a campus network segment; determines which power system to query |
| **roomId** | Hidden database primary key for a room; discovered via web scraping, not derivable from room number |
| **Pending subscription** | Submitted but awaiting email verification (`enabled=true, verified=false`) |
| **Active subscription** | Verified and receiving alerts (`enabled=true, verified=true`) |
| **Alert sweep** | One complete pass evaluating all eligible subscriptions |
| **Room key** | Composite identifier `(client, campus_name, building_id, room_name)` used for grouping optimizations |
| **Atomic write** | Write-via-temporary-then-rename pattern ensuring crash-consistency |
| **Thin wrapper** | Legacy file that merely re-exports symbols from the canonical `electrifyszu/` package |
