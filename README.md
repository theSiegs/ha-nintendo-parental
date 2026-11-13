# Nintendo Switch parental controls (patched)

A HACS custom integration that **replaces Home Assistant's built-in
`nintendo_parental_controls` integration** with a patched copy of it.

It is the core integration from Home Assistant 2026.11.0, under the same
domain, plus a small set of fixes. Because the domain is the same:

- Home Assistant loads this copy instead of the built-in one (it logs a
  warning that a custom integration overrides a core integration; that is
  expected).
- Your existing config entry, devices, entity IDs and unique IDs are reused
  as they are. Nothing needs to be set up again.
- **Uninstalling reverts to the built-in integration.** Remove it in HACS (or
  delete `custom_components/nintendo_parental_controls`) and restart; Home
  Assistant goes back to the core version with the same config entry. Entities
  added by this copy (see below) become unavailable and can be deleted,
  automations that pass `key_by_player_id` to `device_usage_report` must drop
  it, because core rejects the unknown field, and automations that call
  `cancel_bonus_time`, `list_applications` or `set_app_allowed` stop
  working, because core has no such actions.

Every fix here is meant to be upstreamed to Home Assistant core, one pull
request per fix; see [UPSTREAM.md](UPSTREAM.md). Once a fix lands in core, it
is dropped from this repository. The goal is for this repository to become
unnecessary.

## Installation

1. In HACS, add this repository as a custom repository (category
   *Integration*).
2. Install **Nintendo Switch parental controls (patched)**.
3. Restart Home Assistant.

If you have not set up the integration yet, add it from
**Settings > Devices & services** as usual; setup is the same as for the
built-in integration.

Built from and tested against Home Assistant 2026.11.0. Library versions are
the same as core's: `pynintendoparental==2.6.2` and `pynintendoauth==1.0.3`.
Later Home Assistant releases may need this repository to be rebased on the
newer core integration.

## Changes from core

### Playing now (new binary sensors)

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
Configure**. Expect the sensors to turn on a few minutes after play starts and
to stay on up to the hold-over period after it stops. The first poll after a
restart only records a baseline, and the daily reset at midnight does not
count as play.

### New consoles and players are added without a reload

Core only creates entities at setup, so a console paired later, a new player
profile, or players Nintendo only starts returning later (see below) needed
an integration reload. Entities for them are now added on the next poll.
([core issue #182387](https://github.com/home-assistant/core/issues/182387))

Note: the library (`pynintendoparental`) only learns about players from the
latest monthly summary, which Nintendo returns as "not found" until a console
has about a month of data. Until then no per-player entities exist; with
this change they appear on their own once the summary becomes available.

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
starts and Home Assistant asks you to sign in to Nintendo again. If the new login
works, it simply retries, because Nintendo also rejects valid tokens now and
then (HTTP 401 `invalid_token`).

### Clear errors from actions and controls

Changing the number, switch, select or time entities, or calling
`add_bonus_time`, `update_pin_code` or `update_daily_restrictions`, used to
fail with a raw library exception (or an "unknown error" in the UI) when
Nintendo refused the change, for example while extra playing time is active.
These now raise translated errors: a validation error for things the user can
fix (extra playing time active, wrong restriction mode, out-of-range values)
and a Home Assistant error for communication problems.

### `device_usage_report` keyed by player ID (opt-in)

The `nintendo_parental_controls.device_usage_report` response is keyed by
player nickname, so two players with the same nickname overwrite each other.
The default response is unchanged. Pass `key_by_player_id: true` to get the
report keyed by player ID instead, with the nickname inside:

```yaml
action: nintendo_parental_controls.device_usage_report
data:
  device_id: 1234567890abcdef1234567890abcdef
  key_by_player_id: true
```

```yaml
# default (key_by_player_id: false)
Alex:
  - name: Some Game
    playing_time: 45
    image: https://...
    whitelisted: true
# key_by_player_id: true
a1b2c3d4e5f60708:
  nickname: Alex
  apps:
    - name: Some Game
      playing_time: 45
      image: https://...
      whitelisted: true
```

### Cancel extra playing time (new action and button)

Core can grant extra playing time but not take it back. This copy adds:

| Entity / action | Unique ID |
| --- | --- |
| `button.<switch>_cancel_extra_playing_time` | `{device_id}_cancel_extra_playing_time` |
| `nintendo_parental_controls.cancel_bonus_time` | |

The action takes a `device_id`, like `add_bonus_time`, and can return a
response:

```yaml
action: nintendo_parental_controls.cancel_bonus_time
data:
  device_id: 1234567890abcdef1234567890abcdef
response_variable: result
# result:
#   cancelled: true
#   previous_extra_playing_time: 30   # minutes, -1 if it was unlimited
```

If no extra playing time is active, the action does nothing and returns
`cancelled: false` (and `previous_extra_playing_time: null`), so automations
can call it without checking first. The button instead raises an error saying
there is nothing to cancel. Both decide from the last poll (every 60 seconds),
so extra time granted in Nintendo's app moments ago may not be seen yet.

### Last synced (new diagnostic sensor)

| Entity | Unique ID |
| --- | --- |
| `sensor.<switch>_last_synced` | `{device_id}_last_sync` |

A timestamp of when the console last applied its parental control settings,
as Nintendo reports it (`synchronizedAt`). After changing a limit, bedtime or
bonus time, automations can wait for this to move past the time of the change
to know the console has the new setting. It is read on each poll, so it lags
by up to the polling interval, and only moves when the console is online and
syncs. The sensor is in the diagnostic category.

### Allow list (new actions)

The allow list (Nintendo's app: *Restricted Software*, `safeLaunch` in the
API) lets a game be played even though the console's age rating restriction
would block it. It does not change play time limits or bedtime, and it applies
to the whole console, for every player. Core shows it only as `whitelisted` in
the usage reports. This copy adds two actions, without per-app entities:

| Action | |
| --- | --- |
| `nintendo_parental_controls.list_applications` | Lists the console's applications with their Nintendo application ID and whether each is allowed. |
| `nintendo_parental_controls.set_app_allowed` | Adds an application to, or removes it from, the allow list. Administrators only. |

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
  `list_applications` (case does not matter). Titles can repeat and change
  with the language, so they are not accepted. An unknown ID is refused with a
  translated error.
- The applications are the ones Nintendo lists for the console's allow list:
  software that has been on the console. `list_applications` uses the last
  poll (every 60 seconds); software Nintendo stops listing stays in the list
  until Home Assistant restarts, and `set_app_allowed` refuses it.
- **No stale overwrite.** The library sends the console's whole restriction
  settings (allow list and age rating level) back to Nintendo. So that a
  change made in Nintendo's app since the last poll is not undone,
  `set_app_allowed` first refreshes that console from Nintendo, then writes
  only if the application's state differs (`changed: false` otherwise). If the
  refresh fails, nothing is written. The response is read from the settings
  Nintendo returns after the write, and the entities are updated with the
  refreshed data.
- The console applies the change when it next syncs with Nintendo, as with
  any other setting.

### Diagnostics

Download diagnostics from the integration page. They show each console's
state, update status, restriction settings and the playing inference, with
the session token, console name, serial number, player nicknames and images
redacted.

### Wider `add_bonus_time` range, with a response

Core's `add_bonus_time` only accepted 5 to 30 minutes, while Nintendo's app
now also offers an hour and the library accepts any number of minutes. The
action now accepts **5 to 360 minutes, or -1 for unlimited playing time for
the rest of the day**, and can return the extra playing time Nintendo reports
afterwards (minutes, -1 for unlimited):

```yaml
action: nintendo_parental_controls.add_bonus_time
data:
  device_id: 1234567890abcdef1234567890abcdef
  bonus_time: 60
response_variable: result
# result:
#   extra_playing_time: 60
```

The UI selector shows -1 to 360 (a selector holds a single range); 0 to 4 are
refused with an error. Notes:

- **Bedtime:** when a bedtime alarm is set for today (and alarms are
  visible), the library grants the minutes against bedtime, so bedtime moves
  later instead of the daily limit growing. -1 always uses Nintendo's
  "unlimited" request.
- **Nintendo may cap it:** 360 matches the longest daily limit Nintendo
  allows; it is not known whether Nintendo's server accepts or caps grants the
  app does not offer (it offers 5, 15, 30 and 60 minutes). Check the response
  or the "Extended screen time" sensor.
- The entities pick the change up on the next poll.
- Core automations without `response_variable` keep working unchanged.

## Known limitations

- **Monthly summary is still fetched on every poll.** `pynintendoparental`
  (2.6.2, and 2.6.3, the latest release) fetches the monthly summary inside
  `Device.update()` on every update, which costs two extra requests per
  console every 60 seconds, and offers no way to skip it. Fetching it at most
  hourly needs a library change; see [UPSTREAM.md](UPSTREAM.md). This
  repository does not monkey-patch the library to work around it.
- The playing sensors are inferred from play time; see above.

## Development

Tests are core's own tests for the integration, plus tests for each fix. They
run with [`pytest-homeassistant`](https://github.com/home-assistant/core/tree/dev/packages/pytest-homeassistant),
pinned to the same Home Assistant release (Python 3.14):

```shell
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

Core's tests are copied from `tests/components/nintendo_parental_controls`
with two changes:

- imports point at `custom_components.nintendo_parental_controls` instead of
  `homeassistant.components.nintendo_parental_controls`;
- `conftest.py`: the mocked device keeps its registered callbacks and the
  mocked `NintendoParental.update()` runs them, as the library does after a
  successful update (needed for the stale-data fix).

Core's test files are otherwise unchanged; each fix adds its own test file.
The one exception is a snapshot: `snapshots/test_sensor.ambr` also holds the
"Last synced" sensor, because core's `test_sensor` snapshots every sensor.

`translations/en.json` is generated from `strings.json`:

```shell
python script/gen_translations.py path/to/core/homeassistant/strings.json
```

## License

Apache-2.0, like Home Assistant core. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).
