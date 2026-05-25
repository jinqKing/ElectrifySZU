<p align="center">
  <img src="https://img.shields.io/badge/version-2.7182-2563eb?style=flat-square" alt="version">
  <img src="https://img.shields.io/badge/python-3.11+-0f9f6e?style=flat-square" alt="python">
  <img src="https://img.shields.io/badge/license-MIT-617083?style=flat-square" alt="license">
  <img src="https://img.shields.io/badge/tests-19%20passed-0f9f6e?style=flat-square" alt="tests">
</p>

<h1 align="center">ElectrifySZU</h1>

<p align="center">
  <a href="https://www.iotun.com"><img src="https://img.shields.io/badge/🚀 Live Demo-www.iotun.com-eab308?style=for-the-badge" alt="官网"></a>
  <a href="http://129.204.227.179/"><img src="https://img.shields.io/badge/💻 Server-http%3A//129.204.227.179-eab308?style=for-the-badge" alt="直连"></a>
</p>

<p align="center">
  <strong style="font-size: 1.3em;">👆 点击上方卡片立即体验在线版 👆</strong>
</p>

<p align="center">
  <strong>深大宿舍电费，不再只有断电时才知道。<br>
  一次查询看到余额、趋势和预警，把校园电费系统变成一个真正的管家。</strong>
</p>

<p align="center">
  <a href="https://www.iotun.com">
    <img src="web/pic/og-image.png" alt="ElectrifySZU" width="600">
  </a>
</p>

***

## 📚 Documentation

| Document | Audience | Covers |
|----------|----------|--------|
| [API Reference](docs/API_REFERENCE.md) | Developers | All endpoints, request/response schemas, error codes |
| [Configuration](docs/CONFIGURATION.md) | Operators | Environment variables, scenario profiles, CLI flags |
| [Architecture](docs/ARCHITECTURE.md) | Contributors | Module map, dual-layer explanation, design decisions |
| [Developer Guide](docs/DEVELOPER-GUIDE.md) | Contributors | Setup, testing, branching, committing, debugging |
| [Security](docs/SECURITY.md) | Auditors | Attack surface, protections, known limitations |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Everyone | Symptom index, diagnostics, recovery procedures |
| [Subscription Flow](docs/SUBSCRIPTION_FLOW.md) | Contributors | End-to-end lifecycle with Mermaid diagrams |

***

## 📖 Overview

Shenzhen University's dorm electricity systems are fragmented across intranet portals and WeChat miniapps — each requiring campus-Network access, showing no history, and providing zero proactive warnings.

**Every surveyed student said the same thing: *"We only pay when the power cuts out. We never know what's left."***

ElectrifySZU consolidates query, trending, and alerting into one dashboard.

| Pain Point | Today | With ElectrifySZU |
|------------|-------|--------------------|
| Query entry | Multiple systems, deep nesting | One page: pick building + room |
| Balance trend | Invisible | 30-day line + bar charts |
| Low-battery alert | None | Automated email, once/day max |
| Campus-net restriction | Mandatory | Public gateway + campus relay |
| Showcase | Nothing | `web/` deploys to GitHub Pages instantly |

## Feature Summary

```text
┌─────────────────────────────────────────────────────────┐
│  Frontend Dashboard (web/)                              │
│  • Bilingual SPA (zh-CN / en-US)                        │
│  • Search + one-click balance/trend query               │
│  • Metric cards: balance / avg usage / days left        │
│  • Interactive charts with usage-level explorer         │
│  • Built-in demo data for offline preview               │
├─────────────────────────────────────────────────────────┤
│  Community Engagement (server.py + web/)                │
│  • Frictionless one-time likes, signed server-side      │
│  • Live footers showing engagement metrics              │
├─────────────────────────────────────────────────────────┤
│  Email Alert Subscriptions (subscription_alerts/)       │
│  • Double opt-in verification                           │
│  • Low-balance warnings + optional daily reports        │
│  • One-click unsubscribe                                │
├─────────────────────────────────────────────────────────┤
│  Backend API Proxy (server.py)                          │
│  • 18 endpoints covering status, buildings, subs,      │
│    likes, health checks, and GitHub star tracking       │
├─────────────────────────────────────────────────────────┤
│  CLI Toolkit                                            │
│  • Dorm:  status / json / discover                      │
│  • Apartment: buildings / floors / rooms / usage       │
│  • Ranking: cache-builder / floor-probe                 │
└─────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
git clone https://github.com/jinqKing/ElectrifySZU.git
cd ElectrifySZU

uv sync
cp .env.example .env
# Edit .env — fill campus network params + SMTP config

uv run server.py
```

Then open `http://127.0.0.1:8000`. Off-campus? Click "载入演示" for a full preview.

### CLI Queries

```bash
# Dorm (粤海/新斋区)
uv run python -m electrifyszu.dorm.cli status
uv run python -m electrifyszu.dorm.discover "<paste_URL>"

# Apartment (丽湖)
cd apartment-power-monitor
python -m src.cli status 01 501
python -m src.cli json 01 501

# Email delivery test
uv run electrifyszu-delivery-test --to you@email.szu.edu.cn
```

More details → [Configuration Guide](docs/CONFIGURATION.md) · [Developer Guide](docs/DEVELOPER-GUIDE.md)

### Run Tests

```bash
uv run pytest -v
```

## Architecture

```text
Browser ↔ Nginx ↔ ElectrifySZU ↔ Campus Relay ↔ Power Systems
                         ↕
                       SMTP
```

Core modules: `electrifyszu/server/` (routing), `electrifyszu/dorm/` (campus API), `electrifyszu/subscription/` (alerts), `electrifyszu/apartment/` (LiHu adapter), `electrifyszu/ranking/` (leaderboards).

Details → [Architecture Overview](docs/ARCHITECTURE.md)

## Deployment Options

| Approach | Best For | See |
|----------|----------|-----|
| Local (`uv run server.py`) | Development | [.env.example](.env.example) |
| Docker Compose | Campus server | [compose.yml](compose.yml) + [Dockerfile](Dockerfile) |
| Nginx reverse proxy | Public internet | [nginx conf](deploy/nginx/electrifyszu.conf) |
| GitHub Pages | Static showcase only | [.github/workflows/pages.yml](.github/workflows/pages.yml) |

Full profiles for each scenario → [Configuration § Scenario Profiles](docs/CONFIGURATION.md#scenario-profiles)

## API Endpoints

18 endpoints across 5 domains. Quick highlights:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/status` | Query balance & trends |
| GET | `/api/buildings` | Campus/building catalog |
| POST | `/api/subscriptions` | Register alert subscription |
| POST | `/api/alerts/check` | Manual alert sweep (admin) |
| GET | `/api/health` | Health probe |

Complete spec with schemas, auth, and error codes → [API Reference](docs/API_REFERENCE.md)

## Known Limitations

- `roomId` and `roomName` must precisely match; typos cause silent failures.
- If the host cannot reach `DORM_API_BASE`, real queries and alerts are blind.
- GitHub Pages hosts static frontend only — no backend capabilities.
- Rate limiting relies on outer Nginx layer; bare-server deployments need manual config.
- No CAPTCHA on subscription form (manageable at current scale).

## Credits

Developed by the **Matrix Team** — Shenzhen University students who also suffer from surprise blackouts.

- [Feishu Wiki](https://my.feishu.cn/wiki/EuOXwd1Efi0uLCktmx7cIocynBb)
- [Team Introduction Slides](web/work-intro.html)
- Found this helpful? Give us a ⭐!

## License

MIT License © Matrix Team
