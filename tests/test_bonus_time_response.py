"""Test the widened add_bonus_time range and its response."""

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from . import setup_integration
from custom_components.nintendo_parental_controls.const import ATTR_BONUS_TIME, DOMAIN
from custom_components.nintendo_parental_controls.services import (
    NintendoParentalService,
)


async def _device_id(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
) -> str:
    """Set up the integration and return the console's device ID."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    return device_entry.id


@pytest.mark.parametrize(
    ("bonus_time", "reported"), [(5, 5), (60, 60), (360, 360), (-1, -1)]
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_add_bonus_time_response(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    bonus_time: int,
    reported: int,
) -> None:
    """The response holds the extra playing time after the change."""
    mock_nintendo_device.extra_playing_time = None
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    async def add_extra_time(minutes: int) -> None:
        # The library re-reads the settings after granting the time.
        mock_nintendo_device.extra_playing_time = reported

    mock_nintendo_device.add_extra_time.side_effect = add_extra_time

    response = await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.ADD_BONUS_TIME,
        {ATTR_DEVICE_ID: device_id, ATTR_BONUS_TIME: bonus_time},
        blocking=True,
        return_response=True,
    )

    mock_nintendo_device.add_extra_time.assert_awaited_once_with(bonus_time)
    assert response == {"extra_playing_time": reported}


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_add_bonus_time_without_response(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """The response is optional, so existing automations keep working."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    assert (
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.ADD_BONUS_TIME,
            {ATTR_DEVICE_ID: device_id, ATTR_BONUS_TIME: 15},
            blocking=True,
        )
        is None
    )
    mock_nintendo_device.add_extra_time.assert_awaited_once_with(15)


@pytest.mark.parametrize("bonus_time", [0, 1, 4])
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_add_bonus_time_below_minimum(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    bonus_time: int,
) -> None:
    """Values between -1 and the minimum are refused with a clear error."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.ADD_BONUS_TIME,
            {ATTR_DEVICE_ID: device_id, ATTR_BONUS_TIME: bonus_time},
            blocking=True,
        )
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "bonus_time_out_of_range"
    assert err.value.translation_placeholders == {
        "value": str(bonus_time),
        "min": "5",
        "max": "360",
    }
    mock_nintendo_device.add_extra_time.assert_not_called()
