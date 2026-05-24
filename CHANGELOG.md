# Changelog

All notable changes to ElectrifySZU will be documented in this file.

The format follows the spirit of Keep a Changelog, and this project uses an Euler-number-inspired version sequence that converges toward `e`.

## [2.7183] - 2026-05-25

### Added

- **丽湖公寓模块** (`apartment-power-monitor/`): 适配 `http://172.25.100.105:8010/` 的 ASP.NET 公寓电费系统，支持梧桐树、青冈栎、三角梅、冬青树、紫罗兰、B3文韬楼（丽湖）等6栋楼的楼栋-楼层-房间级联查询、电费状态、充值记录与30天用电趋势。

## [2.7182] - 2026-05-25

### Highlights

- **Online launch!** 🔗 Access the live system at [www.iotun.com](https://www.iotun.com) or directly via [129.204.227.179](http://129.204.227.179/).
- Major frontend refactoring: modularized JS, lazy-loaded dependencies, improved performance and UX throughout.

### Added

- Added live demo badges to README linking to production deployments.
- Redesigned subscription panel with cleaner layout and better form interaction.
- Added GitHub star counter displayed in the page footer.
- Added three-column action bar: GitHub repo link, sponsorship QR, and quick recharge shortcut.
- Applied loading animation when submitting subscription forms.
- Animated opening of building dropdown on first page visit for better discovery.
- Hero status immediately shows "Loading..." placeholder on page load.
- Multi-scenario rotation for demo data (more realistic preview scenarios).
- Balance card color dynamically reflects power status (normal/warning/critical).
- Auto-detect email domain based on student ID year (`@mail.szu.edu.cn` vs `@szu.edu.cn`).

### Changed

- Refactored monolithic `app.js` into ES Modules (`modules/app-core.js`, `modules/buildings.js`, `modules/chart.js`, `modules/subscription.js`).
- Lazy-load chart.js library and subscription module only when needed, reducing initial bundle size.
- Removed inline loading states from hero status element.
- Cached building data in `localStorage` to avoid redundant network requests.
- Cleaned up CSS: removed unnecessary `max-width` constraints causing premature line breaks.
- Updated README with production URLs, clarified setup instructions, and bumped version badge to `2.7182`.

### Fixed

- Resolved three P0 bugs in the balance trend chart (tooltip clipping, axis overflow, rendering glitches).
- Prevented building dropdown from auto-opening on initialization.
- Supported alternate column names in purchase-series recharge records, fixing multi-building report parsing.
- Clamped estimated remaining days to minimum of 0 (prevents negative display).

## [2.718] - 2026-05-22

### Security

- Hardened API request boundaries in `server.py` with stricter POST body parsing, same-origin checks for browser POST endpoints, stronger like-ID validation, and redacted sensitive query values in access logs.
- Changed `/api/alerts/check` from unauthenticated `GET` to authenticated `POST` using `X-Admin-Token` and `ALERT_ADMIN_TOKEN`.

### Reliability

- Made `data/likes.json` writes atomic.
- Switched subscription CSV writes to unique temp files with flush/fsync + replace semantics.
- Fixed alert batching so subscriptions with the same building and room but different `client` or campus are checked independently.
- Clear expired verification tokens when they are encountered.

### Testing and CI

- Added offline regression tests for server request boundaries and alert grouping.
- Added a GitHub Actions CI workflow that runs `uv sync --extra dev --locked` and `uv run pytest -q`.

### Added

- Added `/api/health` and `/api/version` endpoints for service monitoring and deployment validation.
- Added unified error-code convention across all API routes for consistent client-side handling.
- Added foundational pytest suite covering core business logic and API boundary cases (19 test cases).
- Added free-like feature with per-user deduplication: backend endpoints (`/api/like/init`, `/api/like`, `/api/like/count`, `/api/like/my`) and a thread-safe `data/likes.json` store.
- Added `/api/stats` endpoint exposing aggregate metrics (total likes and active user count).
- Added interactive heart button and live counters in the page footer, fully localized and mobile-responsive.
- Restored hand-edited eight-slide work introduction deck with refined styling and layout.

### Changed

- Rewrote the top-level README with pain-point comparison table, feature overview, architecture diagram, API reference table, and test badges.
- Refactored the monolithic `work-intro.html` (~977 lines) into three clean modules: pure HTML skeleton, external stylesheet (`work-intro.css`), and dedicated JavaScript (`work-intro.js`) with added touch-swipe navigation.
- Updated the project version to `2.718`, continuing the Euler-number-inspired sequence converging toward \(e\).

### Fixed

- Corrected same-room logic so every occupant receives independent results regardless of query order.

## [2.71] - 2026-05-21

### Added

- Added richer homepage branding elements, including the GitHub repository icon link and clearer version presentation in the hero area.
- Added default `@email.szu.edu.cn` completion guidance for low-balance alert subscriptions to reduce input friction.

### Changed

- Bumped the project version to `2.71` as the third release in the Euler-number-inspired version sequence.
- Polished dashboard interactions with clickable metric cards, animated unit switches, and smoother visual feedback when toggling balance and usage views.
- Improved the trend chart experience with better hover and click targets, clearer tooltip details, and more intuitive usage-level exploration.
- Refined loading and status feedback so queries feel more responsive during campus-network requests.
- Extracted and organized frontend i18n copy to make bilingual text management and future UI copy updates easier.

## [2.7] - 2026-05-20

### Changed

- Switched the project version from the initial MVP version to an Euler-number-inspired sequence that converges toward `e`.
- Centralized runtime version labels so server and API headers read from the project version metadata.
- Clarified documentation for static GitHub Pages previews and internal-network full queries.

## [0.1.0] - 2026-05-20

### Added

- Initialized the uv-managed Python project.
- Added the existing `room-power-monitor` crawler/query module.
- Added public project documentation, MIT license, and repository hygiene rules.
- Prepared the project for GitHub collaboration before the dashboard MVP work starts.
- Added the first static dashboard MVP with a local Python API proxy.
- Added demo data support for offline presentation previews.

### Changed

- Made the status query period dynamic instead of hard-coding a single date range.
