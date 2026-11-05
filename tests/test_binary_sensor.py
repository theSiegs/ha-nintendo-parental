"""Test binary sensor platform."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.const import STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import setup_integration
from custom_components.nintendo_parental_controls.const import (
    ATTR_LAST_INCREASE,
    CONF_PLAYING_HOLDOVER,
)

DEVICE_PLAYING = "binary_sensor.home_assistant_test_playing"
PLAYER_PLAYING = "binary_sensor.home_assistant_test_ha_gamer_playing"


@pytest.fixture(autouse=True)
def only_binary_sensor() -> None:
    """Only set up the binary sensor platform."""
    with patch(
        "custom_components.nintendo_parental_controls._PLATFORMS",
        [Platform.BINARY_SENSOR],
    ):
        yield


async def _poll(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, minutes: int
) -> None:
    """Advance time and let the coordinator poll."""
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test the playing binary sensors are created with stable unique IDs."""
    await setup_integration(hass, mock_config_entry)

    device_entry = entity_registry.async_get(DEVICE_PLAYING)
    assert device_entry
    assert device_entry.unique_id == "testdevid_playing"
    player_entry = entity_registry.async_get(PLAYER_PLAYING)
    assert player_entry
    assert player_entry.unique_id == "testdevid_testplayerid_playing"

    for entity_id, name in (
        (DEVICE_PLAYING, "Home Assistant Test Playing"),
        (PLAYER_PLAYING, "Home Assistant Test HA Gamer playing"),
    ):
        state = hass.states.get(entity_id)
        assert state
        # The first poll only sets the baseline.
        assert state.state == STATE_OFF
        assert state.attributes["friendly_name"] == name
        assert state.attributes[ATTR_LAST_INCREASE] is None


async def test_playing_inferred_from_play_time(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Play time growing turns the sensors on until the hold-over expires."""
    await setup_integration(hass, mock_config_entry)

    mock_nintendo_device.today_playing_time = 112
    mock_nintendo_device.get_player("testplayerid").playing_time = 112
    await _poll(hass, freezer, 1)
    increased_at = dt_util.utcnow()

    for entity_id in (DEVICE_PLAYING, PLAYER_PLAYING):
        state = hass.states.get(entity_id)
        assert state.state == STATE_ON
        assert state.attributes[ATTR_LAST_INCREASE] == increased_at

    # No new upload for a while: still assumed to be playing.
    await _poll(hass, freezer, 9)
    assert hass.states.get(DEVICE_PLAYING).state == STATE_ON

    # Hold-over (10 minutes by default) expired.
    await _poll(hass, freezer, 1)
    for entity_id in (DEVICE_PLAYING, PLAYER_PLAYING):
        state = hass.states.get(entity_id)
        assert state.state == STATE_OFF
        assert state.attributes[ATTR_LAST_INCREASE] == increased_at


async def test_reset_at_midnight_is_not_play(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The daily reset of play time does not count as play."""
    await setup_integration(hass, mock_config_entry)

    mock_nintendo_device.today_playing_time = 0
    await _poll(hass, freezer, 1)
    assert hass.states.get(DEVICE_PLAYING).state == STATE_OFF

    mock_nintendo_device.today_playing_time = 3
    await _poll(hass, freezer, 1)
    assert hass.states.get(DEVICE_PLAYING).state == STATE_ON


async def test_holdover_option(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The hold-over period is configurable in the options."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PLAYING_HOLDOVER: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {CONF_PLAYING_HOLDOVER: 30}

    mock_nintendo_device.today_playing_time = 115
    await _poll(hass, freezer, 1)
    assert hass.states.get(DEVICE_PLAYING).state == STATE_ON

    await _poll(hass, freezer, 29)
    assert hass.states.get(DEVICE_PLAYING).state == STATE_ON

    await _poll(hass, freezer, 1)
    assert hass.states.get(DEVICE_PLAYING).state == STATE_OFF
