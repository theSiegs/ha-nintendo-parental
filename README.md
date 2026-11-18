# Nintendo Switch parental controls (patched)

A HACS custom integration that **replaces Home Assistant's built-in
`nintendo_parental_controls` integration** with a patched copy of it.

It is the core integration from Home Assistant core `dev` (2026-11-15, the
code that becomes 2026.12), under the same domain, plus the fixes that are
being proposed upstream. Because the domain is the same:

- Home Assistant loads this copy instead of the built-in one (it logs a
  warning that a custom integration overrides a core integration; that is
  expected).
- Your existing config entry, devices, entity IDs and unique IDs are reused
  as they are. Nothing needs to be set up again.
- **Uninstalling reverts to the built-in integration.** Remove it in HACS (or
  delete `custom_components/nintendo_parental_controls`) and restart; Home
  Assistant goes back to the core version with the same config entry. The
  playing and "Last synced" sensors become unavailable and can be deleted, and
  automations that call `cancel_bonus_time`, `list_applications` or
  `set_app_allowed`, or pass more than 30 minutes (or -1) to
  `add_bonus_time`, stop working, because core does not have them yet.

Every fix here is a pull request (or a draft of one) against Home Assistant
core; see [UPSTREAM.md](UPSTREAM.md). Once a fix ships in a core release, it is
dropped from this repository. The goal is for this repository to become
unnecessary.

## Installation

1. In HACS, add this repository as a custom repository (category
   *Integration*).
2. Install **Nintendo Switch parental controls (patched)**.
3. Restart Home Assistant.

If you have not set up the integration yet, add it from
**Settings > Devices & services** as usual; setup is the same as for the
built-in integration.

Runs on Home Assistant 2026.11 and later (a small fallback in `compat.py`
covers what core `dev` uses from 2026.12). Libraries: `pynintendoparental==2.7.0`
(core still pins 2.6.2) and `pynintendoauth==1.0.3`.

## Changes from core

### Playing now (new binary sensors, this repository only)

This branch (`ha/core-dev-next-playing`) also keeps the inferred playing
sensors. They are not proposed to core; they stay until Hearth infers playing
from core's per-player screen time sensors itself.

| Entity | Unique ID |
| --- | --- |
| `binary_sensor.<switch>_playing` | `{device_id}_playing` |
| `binary_sensor.<switch>_<player>_playing` | `{device_id}_{player_id}_playing` |

Both have a `last_increase` attribute: when the play time was last seen
growing (UTC), or `null` if not since Home Assistant started.

**These are inferred.** Nintendo publishes no "now playing" signal. The
sensors turn on when the day's play time (for the console, or for that
player) grows between two polls, and stay on for a hold-over period after the
last increase, because the console only uploads its play time every few
minutes. The hold-over defaults to 10 minutes and can be changed under
**Settings > Devices & services > Nintendo Switch parental controls >
Configure**. The first poll after a restart only records a baseline, the
daily reset at midnight does not count as play, and a console that failed to
update is not compared.

### Entities go unavailable when a console's data is stale

The library catches and only logs errors while updating a single console, so
core kept showing that console's old values as if they were current. Now a
console whose update failed in the last poll has its entities marked
unavailable until an update succeeds again (a warning is logged once when it
happens, and an info message when it recovers).

### Reauthentication when the login is revoked

Core only asked to reauthenticate if the token was rejected while Home
Assistant was starting; at runtime it retried forever. Now, when Nintendo
rejects the token while polling, the integration logs in again with the
stored session token. If that is refused too, the reauthentication flow
starts and Home Assistant asks you to sign in to Nintendo again. If the new
login works, it simply retries, because Nintendo also rejects valid tokens now
and then (HTTP 401 `invalid_token`).

### Last synced (new diagnostic sensor)

| Entity | Unique ID |
| --- | --- |
| `sensor.<switch>_last_synced` | `{device_id}_last_sync` |

A timestamp of when the console last applied its parental control settings,
as Nintendo reports it (`synchronizedAt`). After changing a limit, bedtime or
bonus time, automations can wait for this to move past the time of the change
to know the console has the new setting. It is read on each poll, so it lags
by up to the polling interval, and only moves when the console is online and
syncs.

### New consoles and players are added without a reload

Core only creates entities at setup, so a console paired later, a new player
profile, or players Nintendo only starts returning later needed an
integration reload. Entities for them are now added on the next poll.
([core issue #182387](https://github.com/home-assistant/core/issues/182387))

From `pynintendoparental` 2.7.0 the library also finds players in the daily
summaries, so a console without a monthly summary yet (Nintendo returns "not
found" until it has about a month of data) gets its per-player entities too.

### `add_bonus_time`: up to 60 minutes, or unlimited

Core's `add_bonus_time` accepts 5 to 30 minutes, and its UI selector offered
-1 to 1440, so most values failed. This copy accepts **5 to 60 minutes, or -1
for unlimited playing time for the rest of the day**, which is what Nintendo's
app offers. Nintendo refuses more than 60 minutes in one request.

```yaml
action: nintendo_parental_controls.add_bonus_time
data:
  device_id: 1234567890abcdef1234567890abcdef
  bonus_time: 60
```

The UI selector shows -1 to 60 (a selector holds a single range); 0 to 4 are
refused. When a bedtime alarm is set for today, the library grants the
minutes against bedtime, so bedtime moves later instead of the daily limit
growing.

### Cancel extra playing time (new action)

Core can grant extra playing time but not take it back. This copy adds
`nintendo_parental_controls.cancel_bonus_time` (administrators only, like the
other actions that change settings):

```yaml
action: nintendo_parental_controls.cancel_bonus_time
data:
  device_id: 1234567890abcdef1234567890abcdef
```

It is always sent to Nintendo, even if the last poll saw no extra playing
time, so time granted in Nintendo's app moments ago is cancelled too.

### Allow list (new actions)

The allow list (Nintendo's app: *Restricted Software*, `safeLaunch` in the
API) lets a game be played even though the console's age rating restriction
would block it. It does not change play time limits or bedtime, and it applies
to the whole console, for every player. Core shows it only as `whitelisted` in
the usage reports. This copy adds two actions, without per-app entities:

| Action | |
| --- | --- |
| `nintendo_parental_controls.list_applications` | Lists the console's applications with their Nintendo application ID and whether each is allowed. |
| `nintendo_parental_controls.set_app_allowed` ("Update allow list") | Adds an application to, or removes it from, the allow list. Administrators only. |

```yaml
action: nintendo_parental_controls.list_applications
data:
  device_id: 1234567890abcdef1234567890abcdef
response_variable: apps
# apps:
#   applications:
#     - application_id: 0100ABCDEF012000
#       name: Some Game
#       allowed: false
#       image: https://...

action: nintendo_parental_controls.set_app_allowed
data:
  device_id: 1234567890abcdef1234567890abcdef
  application_id: 0100ABCDEF012000
  allowed: true
response_variable: result   # optional
# result:
#   application_id: 0100ABCDEF012000
#   name: Some Game
#   allowed: true
#   changed: true
```

Notes:

- **Application IDs, not titles.** `set_app_allowed` takes the ID from
  `list_applications` (case does not matter). An unknown ID is refused with a
  translated error.
- **No stale overwrite.** The library sends the console's whole restriction
  settings (allow list and age rating level) back to Nintendo. So that a
  change made in Nintendo's app since the last poll is not undone,
  `set_app_allowed` first refreshes that console from Nintendo, then writes
  only if the application's state differs (`changed: false` otherwise). If the
  refresh fails, nothing is written.
- The console applies the change when it next syncs with Nintendo, as with
  any other setting.

### Dropped since `install/combined`

The previous build (`install/combined`, on core 2026.11.0) also had inferred
"playing" binary sensors with an options flow, diagnostics, translated errors
for every setter, `key_by_player_id` on `device_usage_report`, a "Cancel extra
playing time" button and responses from `add_bonus_time` /
`cancel_bonus_time`. They are not in this build; see [UPSTREAM.md](UPSTREAM.md)
for why. This branch keeps the playing sensors (above).

## Known limitations

- None known beyond those of core. (The monthly summary, two extra requests
  per console, is now fetched at most hourly instead of on every poll; a
  console that has none yet still asks for it on each poll.)

## Development

Tests are core's own tests for the integration at the matching core branch.
They run with [`pytest-homeassistant`](https://github.com/home-assistant/core/tree/dev/packages/pytest-homeassistant),
pinned to Home Assistant 2026.11.0 (Python 3.14):

```shell
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

Core's tests are copied from `tests/components/nintendo_parental_controls`
with imports pointing at `custom_components.nintendo_parental_controls`
instead of `homeassistant.components.nintendo_parental_controls`.
`tests/__init__.py` also gives Home Assistant 2026.11 the
`CommonServiceArgument` enum that core's tests import. `tests/test_package.py`
is this repository's own (override and translations checks).

`translations/en.json` is generated from `strings.json`:

```shell
python script/gen_translations.py path/to/core/homeassistant/strings.json
```

## License

Apache-2.0, like Home Assistant core. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).
