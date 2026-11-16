# Upstreaming status

This repository is only the install override for one house. The real work
happens as one branch per pull request against `home-assistant/core`, each cut
from core `dev` on its own, and this repository is rebuilt from them.

Nothing has been pushed or opened yet. The core branches live in a local
blobless clone of `home-assistant/core` (`~/ha-core` in WSL); the pull request
texts are drafted separately.

## Branches in this repository

| Branch | What it is | Status |
| --- | --- | --- |
| `ha/core-dev-next` | Core `dev` at `d0ccc62` (2026-11-15) + PRs 3, 4, 12, 2, 11, 10, 13 below, one commit each, + a fork-only fallback for Home Assistant 2026.11 | Built and tested (2026.11.0), not installed |
| `ha/core-dev-next-playing` | `ha/core-dev-next` + the inferred "playing" binary sensors (old PR 1), fork-only | Built and tested, not installed. Install this one while Hearth still reads the playing sensors |
| `install/combined` | Previous build: core 2026.11.0 + old PRs 1-13 stacked | What is installed now; keep for rollback |
| `main` | Previous build without PRs 10-13 | Superseded |

Commit order on `ha/core-dev-next`: import of core `dev` → fallback for
2026.11 → 3 → 4 → 12 → 2 → 11 → 10 → 13 → these notes. Each PR commit is the
same change as its core branch; where two PRs meet (2 with 3 and 12: a new
console's mocked device needs callbacks and `last_sync`), the fix is in the
later commit.

## Pull requests to core

| # | Core branch | What | Type | Status | Depends on |
| --- | --- | --- | --- | --- | --- |
| 8 | `nintendo/bonus-time-selector` | `add_bonus_time` selector matches its 5-30 schema | Bugfix | Draft ready | none |
| 3 | `nintendo/entity-unavailable` | Entities unavailable when a console fails to update; `entity-unavailable: done` | Code quality (Silver) | Draft ready | none |
| 12 | `nintendo/last-synced-sensor` | "Last synced" timestamp sensor (from #159227) | New feature | Draft ready | none |
| 4 | `nintendo/runtime-reauth` | Reauth when the token is rejected at runtime | Bugfix | Draft ready | none |
| 2 | `nintendo/dynamic-devices` | Entities for consoles and players added after setup; `dynamic-devices: done` | New feature (Gold) | Draft ready | Best after library L-a is released and bumped (fully fixes #182387) |
| 11 | `nintendo/bonus-time-range` | `add_bonus_time` 5-60 or -1 (unlimited) | New feature | Draft ready | none; supersedes 8's range (rebase whichever lands second) |
| 10 | `nintendo/cancel-bonus-time` | `cancel_bonus_time` action (admin only, no button) | New feature | Draft ready | library #140 (released) |
| 13 | `nintendo/app-allow-list` | `list_applications` / `set_app_allowed` actions | New feature | Draft ready | none |

Library (`pantherale0/pynintendoparental`), prepared separately:

| # | What | Status |
| --- | --- | --- |
| L-a | Players from daily summaries (fixes core #182387 together with 2) | Separate work |
| L-b | `update(monthly_summary=...)` to skip the monthly summary | Separate work; unblocks 7 |

### Opening order

Library first (L-a, L-b), then core **8**, **3**, **12**, **4**, **2**. Then
**11**, **10**, **13** (10 before 13): these are on the maintainer's roadmap
(library issue #45), so their descriptions say so and offer to let him adapt
or take them over. Keep at most 2-3 core pull requests open at a time.

### Not proposed, or held

| # | What | Why |
| --- | --- | --- |
| 1 | Inferred "playing" binary sensors + options flow | Dropped upstream: inferred state, a state attribute and a new platform in one PR. Hearth will infer playing from core's per-player minutes. Kept fork-only on `ha/core-dev-next-playing` until then |
| 5 | Translated errors for every setter and action | Optional; would need rework to use the library's `error_key`. 10 and 13 handle their own errors |
| 6 | `key_by_player_id` on `device_usage_report` | Held; nothing uses it |
| 7 | Fetch the monthly summary at most hourly | Needs L-b released first |
| 9 | Diagnostics | Optional |

## Rebuilding this repository

1. In the core clone, update `dev`, rebase the open `nintendo/*` branches, and
   merge them into a throwaway combined branch in the order above.
2. Here, branch from the last build, import the integration and tests from
   core `dev` (one commit), keep the 2026.11 fallback while it is needed, and
   apply each combined merge as its own commit, mapping
   `homeassistant/components/nintendo_parental_controls` to
   `custom_components/nintendo_parental_controls`,
   `tests/components/nintendo_parental_controls` to `tests`, and
   `homeassistant.components.nintendo_parental_controls` to
   `custom_components.nintendo_parental_controls` in tests.
3. Regenerate `translations/en.json` (`script/gen_translations.py`) and run
   `pytest`.
4. Drop each PR's commit once it ships in a core release; drop the fallback
   once 2026.12 is the oldest supported release; archive the repository when
   nothing is left.
