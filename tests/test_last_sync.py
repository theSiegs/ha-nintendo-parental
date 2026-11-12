"""Test the last synced sensor."""

from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    STATE_UNKNOWN,
    EntityCategory,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration

LAST_SYNC = "sensor.home_assistant_test_last_synced"


@pytest.fixture(autouse=True)
def only_sensor() -> None:
    """Only set up the sensor platform."""
    with patch(
        "custom_components.nintendo_parental_controls._PLATFORMS",
        [Platform.SENSOR],
    ):
        yield


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_last_sync(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The sensor shows when the console last applied its settings."""
    mock_nintendo_device.last_sync = 1793944800
    await setup_integration(hass, mock_config_entry)

    entry = entity_registry.async_get(LAST_SYNC)
    assert entry
    assert entry.unique_id == "testdevid_last_sync"
    assert entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entry.disabled_by is None
    state = hass.states.get(LAST_SYNC)
    assert state
    assert state.state == "2026-11-06T06:00:00+00:00"
    assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.TIMESTAMP

    # The console applied a newer setting.
    mock_nintendo_device.last_sync = 1793948400.0
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(LAST_SYNC)
    assert state
    assert state.state == "2026-11-06T07:00:00+00:00"


@pytest.mark.parametrize("last_sync", [None, "soon", True])
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_last_sync_missing(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    last_sync: object,
) -> None:
    """A missing or unexpected value is shown as unknown."""
    mock_nintendo_device.last_sync = last_sync
    await setup_integration(hass, mock_config_entry)

    state = hass.states.get(LAST_SYNC)
    assert state
    assert state.state == STATE_UNKNOWN
