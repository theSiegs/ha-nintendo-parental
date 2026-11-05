"""Test library errors raised by actions are translated."""

from datetime import time
from typing import Any
from unittest.mock import AsyncMock

from aiohttp import ClientConnectionError
from pynintendoauth.exceptions import HttpException
from pynintendoparental.exceptions import (
    BedtimeOutOfRangeError,
    DailyPlaytimeOutOfRangeError,
    DeviceError,
    ExtraPlayingTimeActiveError,
    InvalidDeviceStateError,
)
import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.components.time import (
    ATTR_TIME,
    DOMAIN as TIME_DOMAIN,
    SERVICE_SET_VALUE as TIME_SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, CONF_PIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from . import setup_integration
from custom_components.nintendo_parental_controls.const import (
    ATTR_BONUS_TIME,
    ATTR_DAY_OF_WEEK,
    ATTR_MAX_PLAY_TIME,
    DOMAIN,
)
from custom_components.nintendo_parental_controls.services import (
    NintendoParentalService,
)

ENTITY_ACTIONS = [
    pytest.param(
        "update_max_daily_playtime",
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "number.home_assistant_test_max_screentime_today"},
        {ATTR_VALUE: 30},
        id="number",
    ),
    pytest.param(
        "set_restriction_mode",
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.home_assistant_test_suspend_software"},
        {},
        id="switch_on",
    ),
    pytest.param(
        "set_restriction_mode",
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.home_assistant_test_suspend_software"},
        {},
        id="switch_off",
    ),
    pytest.param(
        "set_timer_mode",
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: "select.home_assistant_test_restriction_mode"},
        {ATTR_OPTION: "each_day_of_the_week"},
        id="select",
    ),
    pytest.param(
        "set_bedtime_alarm",
        TIME_DOMAIN,
        TIME_SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: "time.home_assistant_test_bedtime_alarm"},
        {ATTR_TIME: time(20, 0)},
        id="time",
    ),
]

ERRORS = [
    pytest.param(
        ExtraPlayingTimeActiveError(30),
        ServiceValidationError,
        "extra_playing_time_active_settings",
        None,
        id="extra_playing_time_active",
    ),
    pytest.param(
        InvalidDeviceStateError("Invalid device state"),
        ServiceValidationError,
        "invalid_device_state",
        None,
        id="invalid_device_state",
    ),
    pytest.param(
        DailyPlaytimeOutOfRangeError(400),
        ServiceValidationError,
        "daily_playtime_out_of_range",
        {"value": "400"},
        id="daily_playtime_out_of_range",
    ),
    pytest.param(
        DeviceError("Something went wrong"),
        HomeAssistantError,
        "device_error",
        {"error": "Something went wrong"},
        id="device_error",
    ),
    pytest.param(
        HttpException(500, "Internal error"),
        HomeAssistantError,
        "communication_error",
        {"error": "HTTP 500: Internal error"},
        id="http_error",
    ),
    pytest.param(
        ClientConnectionError("Connection reset"),
        HomeAssistantError,
        "communication_error",
        {"error": "Connection reset"},
        id="connection_error",
    ),
]


@pytest.mark.parametrize(
    ("method", "domain", "service", "target", "data"), ENTITY_ACTIONS
)
@pytest.mark.parametrize(
    ("side_effect", "error_type", "translation_key", "placeholders"), ERRORS
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_entity_action_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    method: str,
    domain: str,
    service: str,
    target: dict[str, Any],
    data: dict[str, Any],
    side_effect: Exception,
    error_type: type[HomeAssistantError],
    translation_key: str,
    placeholders: dict[str, str] | None,
) -> None:
    """Library errors from entity actions are raised as translated errors."""
    await setup_integration(hass, mock_config_entry)
    getattr(mock_nintendo_device, method).side_effect = side_effect

    with pytest.raises(error_type) as err:
        await hass.services.async_call(
            domain, service, data, target=target, blocking=True
        )
    assert type(err.value) is error_type
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == placeholders


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_time_bedtime_out_of_range_still_specific(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """The time entity keeps its own message for out of range bedtimes."""
    await setup_integration(hass, mock_config_entry)
    mock_nintendo_device.set_bedtime_alarm.side_effect = BedtimeOutOfRangeError(
        time(12, 0)
    )

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            TIME_DOMAIN,
            TIME_SERVICE_SET_VALUE,
            {ATTR_TIME: time(12, 0)},
            target={ATTR_ENTITY_ID: "time.home_assistant_test_bedtime_alarm"},
            blocking=True,
        )
    assert err.value.translation_key == "bedtime_alarm_out_of_range"


@pytest.mark.parametrize(
    ("method", "service", "data"),
    [
        pytest.param(
            "add_extra_time",
            NintendoParentalService.ADD_BONUS_TIME,
            {ATTR_BONUS_TIME: 15},
            id="add_bonus_time",
        ),
        pytest.param(
            "set_new_pin",
            NintendoParentalService.UPDATE_PIN_CODE,
            {CONF_PIN: "1234"},
            id="update_pin_code",
        ),
        pytest.param(
            "set_daily_restrictions",
            NintendoParentalService.UPDATE_DAILY_RESTRICTIONS,
            {ATTR_DAY_OF_WEEK: "monday", ATTR_MAX_PLAY_TIME: 60},
            id="update_daily_restrictions",
        ),
    ],
)
@pytest.mark.parametrize(
    ("side_effect", "error_type", "translation_key"),
    [
        pytest.param(
            HttpException(500, "Internal error"),
            HomeAssistantError,
            "communication_error",
            id="http_error",
        ),
        pytest.param(
            DailyPlaytimeOutOfRangeError(400),
            ServiceValidationError,
            "daily_playtime_out_of_range",
            id="daily_playtime_out_of_range",
        ),
    ],
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_service_action_errors(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    method: str,
    service: str,
    data: dict[str, Any],
    side_effect: Exception,
    error_type: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Library errors from integration actions are raised as translated errors."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    getattr(mock_nintendo_device, method).side_effect = side_effect

    with pytest.raises(error_type) as err:
        await hass.services.async_call(
            DOMAIN,
            service,
            {ATTR_DEVICE_ID: device_entry.id, **data},
            blocking=True,
        )
    assert type(err.value) is error_type
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
