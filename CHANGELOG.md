# Changelog

All notable changes to ElectrifySZU will be documented in this file.

The format follows the spirit of Keep a Changelog, and this project uses an Euler-number-inspired version sequence that converges toward `e`.

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
