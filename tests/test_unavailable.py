"""Test entities become unavailable when their console fails to update."""

from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from . import setup_integration

ENTITIES = (
    "binary_sensor.home_assistant_test_playing",
    "number.home_assistant_test_max_screentime_today",
    "select.home_assistant_test_restriction_mode",
    "sensor.home_assistant_test_used_screen_time",
    "sensor.home_assistant_test_ha_gamer_used_screen_time",
    "switch.home_assistant_test_suspend_software",
    "time.home_assistant_test_bedtime_alarm",
)


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_device_update_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A device the library fails to update is marked unavailable."""
    await setup_integration(hass, mock_config_entry)
    await _poll(hass, freezer)
    for entity_id in ENTITIES:
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE
    coordinator = mock_config_entry.runtime_data
    last_update = coordinator.device_last_update["testdevid"]

    # The library logs and swallows the error: no callback runs, and the
    # old data stays in place.
    working_update = mock_nintendo_client.update.side_effect
    mock_nintendo_client.update.side_effect = None
    await _poll(hass, freezer)

    for entity_id in ENTITIES:
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    assert coordinator.last_update_success
    assert coordinator.device_last_update["testdevid"] == last_update
    assert "Updating Nintendo device testdevid failed" in caplog.text

    mock_nintendo_client.update.side_effect = working_update
    await _poll(hass, freezer)

    for entity_id in ENTITIES:
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE
    assert "Nintendo device testdevid is available again" in caplog.text


async def test_failed_device_does_not_count_as_play(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Play time is not compared while a device is failing."""
    await setup_integration(hass, mock_config_entry)
    await _poll(hass, freezer)
    coordinator = mock_config_entry.runtime_data

    working_update = mock_nintendo_client.update.side_effect
    mock_nintendo_client.update.side_effect = None
    mock_nintendo_device.today_playing_time = 200
    await _poll(hass, freezer)
    assert coordinator.get_play_activity("testdevid").playing_time == 110

    mock_nintendo_client.update.side_effect = working_update
    await _poll(hass, freezer)
    assert coordinator.get_play_activity("testdevid").last_increase is not None
