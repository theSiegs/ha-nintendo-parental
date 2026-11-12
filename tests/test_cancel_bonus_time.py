"""Test cancelling extra playing time with the action and the button."""

from unittest.mock import AsyncMock, patch

from pynintendoauth.exceptions import HttpException
from pynintendoparental.exceptions import DeviceError
import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, Platform
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import setup_integration
from custom_components.nintendo_parental_controls.const import DOMAIN
from custom_components.nintendo_parental_controls.services import (
    NintendoParentalService,
)

BUTTON = "button.home_assistant_test_cancel_extra_playing_time"


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


@pytest.mark.parametrize("extra_playing_time", [30, -1])
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_bonus_time(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    extra_playing_time: int,
) -> None:
    """Active extra playing time is cancelled and reported in the response."""
    mock_nintendo_device.extra_playing_time = extra_playing_time
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    response = await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.CANCEL_BONUS_TIME,
        {ATTR_DEVICE_ID: device_id},
        blocking=True,
        return_response=True,
    )

    mock_nintendo_device.cancel_extra_time.assert_awaited_once_with()
    assert response == {
        "cancelled": True,
        "previous_extra_playing_time": extra_playing_time,
    }


@pytest.mark.parametrize("extra_playing_time", [None, 0])
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_bonus_time_none_active(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    extra_playing_time: int | None,
) -> None:
    """Without extra playing time the action does nothing and says so."""
    mock_nintendo_device.extra_playing_time = extra_playing_time
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    response = await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.CANCEL_BONUS_TIME,
        {ATTR_DEVICE_ID: device_id},
        blocking=True,
        return_response=True,
    )

    mock_nintendo_device.cancel_extra_time.assert_not_called()
    assert response == {"cancelled": False, "previous_extra_playing_time": None}


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_bonus_time_without_response(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """The response is optional."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    assert (
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.CANCEL_BONUS_TIME,
            {ATTR_DEVICE_ID: device_id},
            blocking=True,
        )
        is None
    )
    mock_nintendo_device.cancel_extra_time.assert_awaited_once_with()


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_bonus_time_invalid_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An unknown device is refused."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.CANCEL_BONUS_TIME,
            {ATTR_DEVICE_ID: "invalid_device"},
            blocking=True,
        )
    assert err.value.translation_domain == HOMEASSISTANT_DOMAIN
    assert err.value.translation_key == "service_device_not_found"


@pytest.mark.parametrize(
    ("side_effect", "translation_key"),
    [
        pytest.param(
            HttpException(500, "Internal error"),
            "communication_error",
            id="http_error",
        ),
        pytest.param(DeviceError("refused"), "device_error", id="device_error"),
    ],
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_bonus_time_errors(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    side_effect: Exception,
    translation_key: str,
) -> None:
    """Library errors are raised as translated errors."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)
    mock_nintendo_device.cancel_extra_time.side_effect = side_effect

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.CANCEL_BONUS_TIME,
            {ATTR_DEVICE_ID: device_id},
            blocking=True,
            return_response=True,
        )
    assert type(err.value) is HomeAssistantError
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_button(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """The button cancels active extra playing time."""
    with patch(
        "custom_components.nintendo_parental_controls._PLATFORMS",
        [Platform.BUTTON],
    ):
        await setup_integration(hass, mock_config_entry)

    entry = entity_registry.async_get(BUTTON)
    assert entry
    assert entry.unique_id == "testdevid_cancel_extra_playing_time"
    assert entry.translation_key == "cancel_extra_playing_time"

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: BUTTON},
        blocking=True,
    )
    mock_nintendo_device.cancel_extra_time.assert_awaited_once_with()


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_button_none_active(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Pressing the button without extra playing time raises a clear error."""
    mock_nintendo_device.extra_playing_time = None
    with patch(
        "custom_components.nintendo_parental_controls._PLATFORMS",
        [Platform.BUTTON],
    ):
        await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: BUTTON},
            blocking=True,
        )
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "no_extra_playing_time"
    mock_nintendo_device.cancel_extra_time.assert_not_called()


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_cancel_button_error(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Library errors from the button are raised as translated errors."""
    mock_nintendo_device.cancel_extra_time.side_effect = HttpException(
        500, "Internal error"
    )
    with patch(
        "custom_components.nintendo_parental_controls._PLATFORMS",
        [Platform.BUTTON],
    ):
        await setup_integration(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: BUTTON},
            blocking=True,
        )
    assert err.value.translation_key == "communication_error"
