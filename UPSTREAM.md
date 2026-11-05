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
