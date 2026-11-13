# Upstreaming plan

Each fix in this repository is a separate commit and is meant to become its
own pull request against `home-assistant/core`
(`homeassistant/components/nintendo_parental_controls`). No pull requests or
issues have been opened yet.

To build a core PR from a commit: cherry-pick it onto core `dev`, move the
files back to `homeassistant/components/nintendo_parental_controls` and
`tests/components/nintendo_parental_controls`, switch test imports back to
`homeassistant.components...`, drop the `translations/en.json` change (core
generates it), and update `quality_scale.yaml` and the documentation in
`home-assistant.io` where noted.

Core's own tests for the integration pass unchanged at every commit, except
for one test-fixture change that comes with PR 3 (the mocked client runs
device callbacks on `update()`, as the library does) and the sensor snapshot
that comes with PR 12 (the new "Last synced" sensor). Tests run with
`pytest-homeassistant` 2026.11.0; `pytest-homeassistant-custom-component` has
no 2026.11 release and now points to that package.

The PRs are independent except where noted: 9 (diagnostics) reports fields
added by 1 and 3, 7 needs a library release first, 10 uses the error helper
from 5, and 11 replaces 8.

added by 1 and 3, 7 needs a library release first, and 13 uses the error
helper from 5.

## Candidate pull requests

### 1. Inferred "playing" binary sensors

- Adds a `binary_sensor` platform: per console (`{device_id}_playing`) and per
  player (`{device_id}_{player_id}_playing`), with a `last_increase`
  attribute, and an options flow for the hold-over period (default 10 min).
- Issue: none open. This is a new feature, so it may need a
  [feature request / architecture discussion](https://github.com/orgs/home-assistant/discussions)
  first. Expect review questions about the state attribute (core discourages
  them; it could become a separate timestamp sensor) and about inferring
  state rather than reading it from the API.
- Docs: document the binary sensors and the option on home-assistant.io.

### 2. Add entities for consoles and players that appear after setup

- Each platform registers a coordinator listener that adds entities for new
  consoles and new players (`async_setup_dynamic_entities` in `entity.py`).
  Marks the `dynamic-devices` quality scale rule as done.
- Issue: [#182387](https://github.com/home-assistant/core/issues/182387).
- Related library change (separate PR to `pantherale0/pynintendoparental`):
  `Device._hydrate_players_from_monthly_summary` is the only place players are
  created, so consoles without a monthly summary (HTTP 404
  `resource_is_not_found`) have no players. Creating players from the daily
  summary as well (`Player.from_device_daily_summary` already exists) would
  fix the rest of #182387.

### 3. Mark entities unavailable when their console fails to update

- `NintendoParental.update()` wraps each `Device.update()` in a broad
  `except Exception` and only logs it, so stale data looked current. The
  coordinator now registers a device callback (the library runs callbacks only
  at the end of a successful `Device.update()`), keeps a last-successful-update
  time per console, and `NintendoDevice.available` is false for consoles not
  updated in the last poll. Marks `entity-unavailable` as done.
- Tests: `conftest.py` makes the mocked client run device callbacks on
  `update()`, like the library does.
- Issue: none open; it is the `entity-unavailable` rule (todo) in the
  integration's `quality_scale.yaml`. Related log noise:
  [#160261](https://github.com/home-assistant/core/issues/160261).
- A cleaner long-term fix is in the library: re-raise, or expose a per-device
  "last updated" / "update failed" flag (`Device.stats_update_failed` exists
  but only covers the remaining-time calculation).

### 4. Start reauthentication when the token is rejected at runtime

- On `InvalidSessionTokenException` or an HTTP 401 while polling, the
  coordinator calls `Authenticator.async_complete_login(use_session_token=True)`;
  if that raises `InvalidSessionTokenException` /
  `InvalidOAuthConfigurationException` it raises `ConfigEntryAuthFailed`
  (reauth flow), otherwise `UpdateFailed`. Core's existing
  `test_update_errors` case for `InvalidSessionTokenException` still passes
  unchanged.
- Issues: [#161104](https://github.com/home-assistant/core/issues/161104),
  [#160261](https://github.com/home-assistant/core/issues/160261) (occasional
  `invalid_token`, which is why a single 401 must not start reauth).
- `reauthentication-flow` is already marked done in `quality_scale.yaml`; this
  makes it work after setup too.

### 5. Translate library errors raised by actions

- New `util.handle_device_errors()` context manager maps
  `ExtraPlayingTimeActiveError`, `InvalidDeviceStateError`,
  `BedtimeOutOfRangeError`, `DailyPlaytimeOutOfRangeError`,
  `InputValidationError` to `ServiceValidationError`, and `DeviceError`,
  `HttpException`, `aiohttp.ClientError`, `TimeoutError` to
  `HomeAssistantError`, all with translation keys. Used by the number, switch,
  select and time setters and by `add_bonus_time`, `update_pin_code` and
  `update_daily_restrictions` (whose specific messages are kept). Marks
  `action-exceptions` as done.
- Issue: none specific; it is the `action-exceptions` rule (todo, "Library
  errors are not handled in custom actions and in switch, number and select
  actions") in `quality_scale.yaml`. Possibly related:
  [#167425](https://github.com/home-assistant/core/issues/167425) (bonus time
  silently doing nothing).

### 6. Option to key `device_usage_report` by player ID

- Adds an optional `key_by_player_id` field (default `false`). When true, the
  response is `{player_id: {"nickname": ..., "apps": [...]}}`; the default
  `{nickname: [...]}` shape is unchanged, so existing automations keep
  working.
- Issue: none open. Core may prefer changing the shape outright (a breaking
  change with a release note) over a flag; the flag keeps this repository a
  drop-in replacement.

### 7. Fetch the monthly summary at most hourly (blocked on the library)

- Not implemented. `Device.update()` in `pynintendoparental` 2.6.2 (and 2.6.3)
  always runs `get_monthly_summary()` alongside the daily summary, settings and
  device fetches: two extra requests per console per 60 s poll for data that
  changes once a month. `NintendoParental.update()` has no parameter to skip
  it, and the integration would have to replace library methods to throttle
  it.
- Needed first, in `pantherale0/pynintendoparental`: an option such as
  `NintendoParental.update(monthly_summary=False)` /
  `Device.update(monthly_summary=False)`, or a built-in refresh interval for
  the monthly summary. Then the coordinator can request it once an hour.
  The same change should create players from the daily summary (see 2).
- Issue: none open.

### 8. Match the `add_bonus_time` selector to its schema

- `services.yaml` offered -1 to 1440 minutes while the action schema only
  accepts 5 to 30 (as its description says), so most values in the UI failed
  validation. The selector is now 5 to 30.
- Issue: none open. Possibly related to
  [#156288](https://github.com/home-assistant/core/issues/156288) /
  [#167425](https://github.com/home-assistant/core/issues/167425) (bonus time
  reported as not working).

### 9. Add diagnostics

- `diagnostics.py` with per-console state, update status, play timer
  regulations and play inference; redacts the session token, console name,
  serial number, player nicknames and images. Marks `diagnostics` as done.
  (In core, drop the play-inference and availability fields if PRs 1 and 3
  are not merged first.)
- Issue: none; it is the `diagnostics` rule (todo) in `quality_scale.yaml`.

### 10. Cancel extra playing time

- Adds a `cancel_bonus_time` action (`device_id`, optional response
  `{"cancelled": bool, "previous_extra_playing_time": minutes | -1 | None}`)
  and a per-console "Cancel extra playing time" button (`button` platform,
  `{device_id}_cancel_extra_playing_time`), both calling
  `Device.cancel_extra_time()` (API status `TO_CANCELLED`). Library errors go
  through `handle_device_errors()` (needs 5; without it, drop the wrapper).
- With no extra playing time active (per the last poll) nothing is sent to
  Nintendo: the action returns `cancelled: false` so automations need no
  check; the button raises a `ServiceValidationError`
  (`no_extra_playing_time`). Reviewers may prefer one behaviour for both.
- Issue: none open. Core may want the button alone, or the action alone.
- Docs: document the action, its response and the button.

### 11. Widen the `add_bonus_time` range and return the result

- Schema and selector -1 to 360 minutes; the action refuses 0 to 4 with a
  translated `bonus_time_out_of_range` error (a selector holds one range, so
  -1 for "unlimited" and a minimum of 5 cannot both be expressed). Optional
  response `{"extra_playing_time": minutes | -1 | None}` read after the
  library re-fetches the settings. Strings note that a set bedtime alarm makes
  the bonus extend bedtime instead (library behaviour).
- Supersedes 8 (the selector fix); `tests/test_bonus_time.py` from 8 is updated
  to the new bounds. Upstream, submit either 8 alone or this instead.
- Bounds are a judgement call: Nintendo's app offers 5, 15, 30 and 60
  minutes; 360 matches the longest daily limit; the server's own limit is
  unknown. The original core selector was -1 to 1440, so -1 (`TO_INFINITY`)
  looks intended. Reviewers may want 5 to 60 to match the app.
- Issues: possibly [#167425](https://github.com/home-assistant/core/issues/167425)
  / [#156288](https://github.com/home-assistant/core/issues/156288).

### 12. "Last synced" timestamp sensor

- New diagnostic `SensorDeviceClass.TIMESTAMP` sensor per console
  (`{device_id}_last_sync`) from `Device.last_sync`
  (`synchronizedParentalControlSetting.synchronizedAt`, Unix seconds), so
  automations can tell when a written setting reached the console. Values
  that are not numbers are shown as unknown.
- Tests: `test_last_sync.py`; core's `test_sensor.py` snapshot gains the new
  entity (shown as unknown, since the mocked device has no `last_sync`
  number). Upstream, set `mock.last_sync` in `conftest.py` and regenerate the
  snapshot instead.
- Issue: none open. Docs: list the sensor.

### 13. Allow list actions

- Adds `list_applications` (response only:
  `{"applications": [{"application_id", "name", "allowed", "image"}]}` from
  `Device.applications`) and `set_app_allowed` (admin, `device_id`,
  `application_id`, `allowed`; optional response
  `{"application_id", "name", "allowed", "changed"}`) using
  `Application.set_safe_launch_setting(SafeLaunchSetting.ALLOW / NONE)`.
  Services rather than per-app entities, as the maintainer preferred in
  [core PR #173160](https://github.com/home-assistant/core/pull/173160).
- `set_app_allowed` awaits `Device.update()` before writing, because the
  library sends the whole restriction settings (`whitelistedApplicationList`,
  `functionalRestrictionLevel`, with the settings etag) back through
  `updateRestrictionLevel`; a change made in Nintendo's app since the last
  poll would otherwise be overwritten. It writes only if the state differs,
  then calls `async_update_listeners()`; the library re-parses the settings
  Nintendo returns, so the response shows Nintendo's state. Costs one
  device refresh (about five requests) per call.
- Errors: unknown ID and the library's `LookupError` (no longer in the
  allow list) are `application_not_found` (`ServiceValidationError`); its
  `ValueError` (settings not loaded yet) is `allow_list_unavailable`; the rest
  go through `handle_device_errors()` (needs 5; without it, drop the wrapper).
- Review questions to expect: admin-only (chosen because it bypasses the age
  rating), whether `list_applications` should be folded into
  `device_usage_report` (not done: that report only lists apps played today
  and core's snapshot would change), and whether a cheaper settings-only
  refresh should be added to the library (`Device._get_parental_control_setting`
  is private).
- Tests: `test_app_allow_list.py`. Issue: none open. Docs: document both
  actions and that the allow list is console-wide and does not affect play
  time.
