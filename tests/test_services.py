"""Test Nintendo Parental Controls service calls."""

from datetime import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import probatio
from pynintendoauth.exceptions import HttpException
from pynintendoparental.application import Application
from pynintendoparental.enum import SafeLaunchSetting
from pynintendoparental.exceptions import (
    BedtimeOutOfRangeError,
    ExtraPlayingTimeActiveError,
    InvalidDeviceStateError,
)
import pytest
from pytest_homeassistant.common import MockConfigEntry, MockUser
from syrupy.assertion import SnapshotAssertion

from custom_components.nintendo_parental_controls.const import (
    BEDTIME_ALARM_DISABLE,
    BEDTIME_ALARM_MAX,
    BEDTIME_ALARM_MIN,
    BEDTIME_END_TIME_MAX,
    BEDTIME_END_TIME_MIN,
    DOMAIN,
)
from custom_components.nintendo_parental_controls.services import (
    NintendoParentalService,
    NintendoParentalServiceArgument,
)
from homeassistant.const import CommonServiceArgument
from homeassistant.core import DOMAIN as HOMEASSISTANT_DOMAIN, Context, HomeAssistant
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.service import async_get_all_descriptions

from . import setup_integration
from .const import PLAYER_ENTITY_ID


async def test_add_bonus_time(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Test add bonus time service."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.ADD_BONUS_TIME,
        {
            CommonServiceArgument.DEVICE_ID: device_entry.id,
            NintendoParentalServiceArgument.BONUS_TIME: 15,
        },
        blocking=True,
    )
    assert len(mock_nintendo_device.add_extra_time.mock_calls) == 1


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_add_bonus_time_selector_matches_schema(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test the bonus time selector covers the values the action accepts."""
    await setup_integration(hass, mock_config_entry)
    descriptions = await async_get_all_descriptions(hass)
    selector = descriptions[DOMAIN][NintendoParentalService.ADD_BONUS_TIME]["fields"][
        NintendoParentalServiceArgument.BONUS_TIME
    ]["selector"]["number"]
    assert (selector["min"], selector["max"]) == (-1, 60)


@pytest.mark.parametrize(
    ("bonus_time", "valid"),
    [
        (-2, False),
        (-1, True),
        (0, False),
        (4, False),
        (5, True),
        (60, True),
        (61, False),
    ],
)
async def test_add_bonus_time_range(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    bonus_time: int,
    valid: bool,
) -> None:
    """Test add bonus time accepts 5 to 60 minutes, or -1 for unlimited."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    call = hass.services.async_call(
        DOMAIN,
        NintendoParentalService.ADD_BONUS_TIME,
        {
            CommonServiceArgument.DEVICE_ID: device_entry.id,
            NintendoParentalServiceArgument.BONUS_TIME: bonus_time,
        },
        blocking=True,
    )
    if valid:
        await call
        mock_nintendo_device.add_extra_time.assert_awaited_once_with(bonus_time)
    else:
        with pytest.raises(probatio.Invalid):
            await call
        mock_nintendo_device.add_extra_time.assert_not_called()


@pytest.mark.parametrize(
    ("service", "payload", "return_response", "exception_domain", "exception_key"),
    [
        (
            NintendoParentalService.ADD_BONUS_TIME,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.BONUS_TIME: 15,
            },
            False,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.UPDATE_PIN_CODE,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.PIN: "1234",
            },
            False,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.UPDATE_PIN_CODE,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.PIN: "123",
            },
            False,
            DOMAIN,
            "invalid_pin_length",
        ),
        (
            NintendoParentalService.UPDATE_PIN_CODE,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.PIN: "123456789",
            },
            False,
            DOMAIN,
            "invalid_pin_length",
        ),
        (
            NintendoParentalService.UPDATE_PIN_CODE,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.PIN: "0000",
            },
            False,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.UPDATE_PIN_CODE,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.PIN: "abc",
            },
            False,
            DOMAIN,
            "invalid_pin_length",
        ),
        (
            NintendoParentalService.CANCEL_BONUS_TIME,
            {CommonServiceArgument.DEVICE_ID: "invalid_device"},
            False,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.DEVICE_USAGE_REPORT,
            {CommonServiceArgument.DEVICE_ID: "invalid_device"},
            True,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.LIST_APPLICATIONS,
            {CommonServiceArgument.DEVICE_ID: "invalid_device"},
            True,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.SET_APP_ALLOWED,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.APPLICATION_ID: "testappid",
                NintendoParentalServiceArgument.ALLOWED: True,
            },
            False,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.PLAYER_USAGE_REPORT,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                CommonServiceArgument.ENTITY_ID: PLAYER_ENTITY_ID,
            },
            True,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
        (
            NintendoParentalService.UPDATE_DAILY_RESTRICTIONS,
            {
                CommonServiceArgument.DEVICE_ID: "invalid_device",
                NintendoParentalServiceArgument.DAY_OF_WEEK: "monday",
            },
            False,
            HOMEASSISTANT_DOMAIN,
            "service_device_not_found",
        ),
    ],
)
async def test_service_no_device_exceptions(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    service: NintendoParentalService,
    payload: dict[str, Any],
    return_response: bool,
    exception_domain: str,
    exception_key: str,
) -> None:
    """Test service exceptions."""
    await setup_integration(hass, mock_config_entry)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, service, payload, blocking=True, return_response=return_response
        )
    assert err.value.translation_domain == exception_domain
    assert err.value.translation_key == exception_key


@pytest.mark.parametrize(
    ("service", "payload", "exception_key"),
    [
        (
            NintendoParentalService.ADD_BONUS_TIME,
            {NintendoParentalServiceArgument.BONUS_TIME: 15},
            "invalid_device",
        ),
        (
            NintendoParentalService.UPDATE_PIN_CODE,
            {NintendoParentalServiceArgument.PIN: 1234},
            "invalid_device",
        ),
    ],
)
async def test_service_invalid_device_exceptions(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    service: NintendoParentalService,
    payload: dict[str, Any],
    exception_key: str,
) -> None:
    """Test service exceptions with a device that is not a valid Nintendo device."""
    await setup_integration(hass, mock_config_entry)
    # Create a device that does not have a Nintendo identifier
    device_entry = device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, "00:11:22:33:44:55")},
    )
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            service,
            {
                **payload,
                CommonServiceArgument.DEVICE_ID: device_entry.id,
            },
            blocking=True,
        )
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == exception_key


async def test_update_pin_code(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Test update pin code service."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.UPDATE_PIN_CODE,
        {
            CommonServiceArgument.DEVICE_ID: device_entry.id,
            NintendoParentalServiceArgument.PIN: "1234",
        },
        blocking=True,
    )
    assert len(mock_nintendo_device.set_new_pin.mock_calls) == 1


@pytest.mark.parametrize(
    ("service", "payload", "func"),
    [
        (
            NintendoParentalService.SET_APP_ALLOWED,
            {
                NintendoParentalServiceArgument.APPLICATION_ID: "testappid",
                NintendoParentalServiceArgument.ALLOWED: False,
            },
            "update",
        ),
        (
            NintendoParentalService.CANCEL_BONUS_TIME,
            {},
            "cancel_extra_time",
        ),
        (
            NintendoParentalService.UPDATE_PIN_CODE,
            {
                NintendoParentalServiceArgument.PIN: "1234",
            },
            "set_new_pin",
        ),
        (
            NintendoParentalService.UPDATE_DAILY_RESTRICTIONS,
            {
                NintendoParentalServiceArgument.DAY_OF_WEEK: "monday",
                NintendoParentalServiceArgument.BEDTIME_START: "20:00",
                NintendoParentalServiceArgument.BEDTIME_END: "22:00",
            },
            "set_daily_restrictions",
        ),
    ],
)
async def test_service_requires_admin(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    hass_read_only_user: MockUser,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    service: NintendoParentalService,
    payload: dict[str, Any],
    func: str,
) -> None:
    """Test that admin-only services require administrator access."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            {**payload, CommonServiceArgument.DEVICE_ID: device_entry.id},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    getattr(mock_nintendo_device, func).assert_not_called()


async def test_get_player_application_report(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test device usage report retrieval."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    player_entity = entity_registry.async_get(PLAYER_ENTITY_ID)
    assert player_entity
    response = await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.PLAYER_USAGE_REPORT,
        {
            CommonServiceArgument.DEVICE_ID: device_entry.id,
            CommonServiceArgument.ENTITY_ID: PLAYER_ENTITY_ID,
        },
        blocking=True,
        return_response=True,
    )
    assert response == snapshot


async def test_get_device_application_report(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    snapshot: SnapshotAssertion,
) -> None:
    """Test device usage report retrieval."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    player_entity = entity_registry.async_get(PLAYER_ENTITY_ID)
    assert player_entity
    response = await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.DEVICE_USAGE_REPORT,
        {
            CommonServiceArgument.DEVICE_ID: device_entry.id,
        },
        blocking=True,
        return_response=True,
    )
    assert response == snapshot


@pytest.mark.parametrize(
    ("service", "payload", "return_response", "exception_domain", "exception_key"),
    [
        (
            NintendoParentalService.PLAYER_USAGE_REPORT,
            {CommonServiceArgument.ENTITY_ID: "sensor.not_found"},
            True,
            DOMAIN,
            "invalid_entity",
        ),
        (
            NintendoParentalService.PLAYER_USAGE_REPORT,
            {
                CommonServiceArgument.ENTITY_ID: "sensor.home_assistant_test_screen_time_remaining"
            },
            True,
            DOMAIN,
            "invalid_player",
        ),
    ],
)
async def test_player_service_failures(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    service: NintendoParentalService,
    payload: dict[str, Any],
    return_response: bool,
    exception_domain: str,
    exception_key: str,
) -> None:
    """Test that player specific services raise expected exceptions."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            service,
            {CommonServiceArgument.DEVICE_ID: device_entry.id, **payload},
            blocking=True,
            return_response=return_response,
        )
    assert err.value.translation_domain == exception_domain
    assert err.value.translation_key == exception_key


async def test_update_daily_restrictions(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Ensure that the daily restrictions update as expected."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.UPDATE_DAILY_RESTRICTIONS,
        {
            CommonServiceArgument.DEVICE_ID: device_entry.id,
            NintendoParentalServiceArgument.DAY_OF_WEEK: "monday",
            NintendoParentalServiceArgument.BEDTIME_START: time(21, 0, 0),
            NintendoParentalServiceArgument.BEDTIME_END: time(9, 0, 0),
            NintendoParentalServiceArgument.MAX_PLAY_TIME: 360,
        },
        blocking=True,
    )
    assert len(mock_nintendo_device.set_daily_restrictions.mock_calls) == 1
    mock_nintendo_device.set_daily_restrictions.assert_called_once_with(
        enabled=True,
        bedtime_enabled=True,
        day_of_week="monday",
        bedtime_start=time(9, 0, 0),
        bedtime_end=time(21, 0, 0),
        max_daily_playtime=360,
    )


@pytest.mark.parametrize(
    ("side_effect", "translation_key", "translation_placeholders"),
    [
        pytest.param(
            InvalidDeviceStateError("Invalid device state"),
            "requires_daily_restrictions",
            None,
            id="requires_daily_restrictions",
        ),
        pytest.param(
            ExtraPlayingTimeActiveError("Extra playing time active"),
            "extra_playing_time_active",
            None,
            id="extra_playing_time_active",
        ),
        pytest.param(
            BedtimeOutOfRangeError("Bedtime out of range"),
            "bedtime_out_of_range",
            {
                "bedtime_alarm_min": BEDTIME_ALARM_MIN,
                "bedtime_alarm_max": BEDTIME_ALARM_MAX,
                "bedtime_end_time_min": BEDTIME_END_TIME_MIN,
                "bedtime_end_time_max": BEDTIME_END_TIME_MAX,
                "bedtime_alarm_disable": BEDTIME_ALARM_DISABLE,
            },
            id="bedtime_out_of_range",
        ),
    ],
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_update_daily_restrictions_exceptions(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    side_effect: Exception,
    translation_key: str,
    translation_placeholders: dict[str, str] | None,
) -> None:
    """Test update daily restrictions raises expected exceptions."""
    mock_nintendo_device.set_daily_restrictions.side_effect = side_effect
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.UPDATE_DAILY_RESTRICTIONS,
            {
                CommonServiceArgument.DEVICE_ID: device_entry.id,
                NintendoParentalServiceArgument.DAY_OF_WEEK: "monday",
                NintendoParentalServiceArgument.MAX_PLAY_TIME: 360,
            },
            blocking=True,
        )
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key
    assert err.value.translation_placeholders == translation_placeholders


@pytest.mark.parametrize("extra_playing_time", [30, -1, None])
async def test_cancel_bonus_time(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    extra_playing_time: int | None,
) -> None:
    """Test cancel bonus time is sent even if the last poll saw none."""
    mock_nintendo_device.extra_playing_time = extra_playing_time
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.CANCEL_BONUS_TIME,
        {CommonServiceArgument.DEVICE_ID: device_entry.id},
        blocking=True,
    )
    mock_nintendo_device.cancel_extra_time.assert_awaited_once_with()


@pytest.mark.parametrize(
    "side_effect",
    [
        HttpException(status_code=500, message="Internal error"),
        TimeoutError(),
    ],
)
async def test_cancel_bonus_time_failure(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    side_effect: Exception,
) -> None:
    """Test a failed cancel raises a translated error."""
    mock_nintendo_device.cancel_extra_time.side_effect = side_effect
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.CANCEL_BONUS_TIME,
            {CommonServiceArgument.DEVICE_ID: device_entry.id},
            blocking=True,
        )
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "cancel_bonus_time_failed"


async def _set_app_allowed(
    hass: HomeAssistant,
    device_id: str,
    application_id: str = "testappid",
    allowed: bool = False,
    return_response: bool = True,
) -> dict[str, Any] | None:
    """Call the set_app_allowed action."""
    return await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.SET_APP_ALLOWED,
        {
            CommonServiceArgument.DEVICE_ID: device_id,
            NintendoParentalServiceArgument.APPLICATION_ID: application_id,
            NintendoParentalServiceArgument.ALLOWED: allowed,
        },
        blocking=True,
        return_response=return_response,
    )


async def _console_device_id(
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


def _store_written_setting(app: MagicMock) -> None:
    """Make the mocked write change the application, like the library does."""

    async def set_safe_launch_setting(setting: SafeLaunchSetting) -> None:
        app.safe_launch_setting = setting

    app.set_safe_launch_setting.side_effect = set_safe_launch_setting


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_list_applications(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Test applications are listed with their ID and allow list state."""
    other = MagicMock(spec=Application)
    other.application_id = "otherappid"
    other.name = "Other Game"
    other.image_url = None
    other.safe_launch_setting = SafeLaunchSetting.NONE
    mock_nintendo_device.applications.add_application(other)
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)

    response = await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.LIST_APPLICATIONS,
        {CommonServiceArgument.DEVICE_ID: device_id},
        blocking=True,
        return_response=True,
    )

    assert response == {
        "applications": [
            {
                "application_id": "testappid",
                "name": "Test Game Name",
                "allowed": True,
                "image": "http://example.com/image.png",
            },
            {
                "application_id": "otherappid",
                "name": "Other Game",
                "allowed": False,
                "image": None,
            },
        ]
    }
    mock_nintendo_device.update.assert_not_called()


@pytest.mark.parametrize(
    ("initial", "allowed"),
    [
        (SafeLaunchSetting.ALLOW, False),
        (SafeLaunchSetting.NONE, True),
    ],
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    mock_nintendo_app: MagicMock,
    initial: SafeLaunchSetting,
    allowed: bool,
) -> None:
    """Test the device is refreshed, then the application's setting is written."""
    mock_nintendo_app.safe_launch_setting = initial
    _store_written_setting(mock_nintendo_app)
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)
    calls: list[str] = []
    mock_nintendo_device.update.side_effect = lambda: calls.append("update")
    write = mock_nintendo_app.set_safe_launch_setting.side_effect

    async def record_write(setting: SafeLaunchSetting) -> None:
        calls.append("write")
        await write(setting)

    mock_nintendo_app.set_safe_launch_setting.side_effect = record_write

    response = await _set_app_allowed(hass, device_id, allowed=allowed)

    assert calls == ["update", "write"]
    mock_nintendo_app.set_safe_launch_setting.assert_awaited_once_with(
        SafeLaunchSetting.ALLOW if allowed else SafeLaunchSetting.NONE
    )
    assert response == {
        "application_id": "testappid",
        "name": "Test Game Name",
        "allowed": allowed,
        "changed": True,
    }


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_ignores_case(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_app: MagicMock,
) -> None:
    """Test application IDs match regardless of case."""
    _store_written_setting(mock_nintendo_app)
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)

    response = await _set_app_allowed(hass, device_id, application_id="TESTAPPID")

    mock_nintendo_app.set_safe_launch_setting.assert_awaited_once_with(
        SafeLaunchSetting.NONE
    )
    assert response
    assert response["application_id"] == "testappid"


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_unchanged(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    mock_nintendo_app: MagicMock,
) -> None:
    """Test nothing is written if the application already has the state."""
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)

    assert await _set_app_allowed(hass, device_id, allowed=True) == {
        "application_id": "testappid",
        "name": "Test Game Name",
        "allowed": True,
        "changed": False,
    }
    mock_nintendo_device.update.assert_awaited_once_with()
    mock_nintendo_app.set_safe_launch_setting.assert_not_called()


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_uses_refreshed_state(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    mock_nintendo_app: MagicMock,
) -> None:
    """Test a change made in Nintendo's app since the last poll is seen."""
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)

    def changed_in_nintendo_app() -> None:
        mock_nintendo_app.safe_launch_setting = SafeLaunchSetting.NONE

    mock_nintendo_device.update.side_effect = changed_in_nintendo_app

    response = await _set_app_allowed(hass, device_id, allowed=False)

    mock_nintendo_app.set_safe_launch_setting.assert_not_called()
    assert response
    assert response["changed"] is False
    assert response["allowed"] is False


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_without_response(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_app: MagicMock,
) -> None:
    """Test the response is optional."""
    _store_written_setting(mock_nintendo_app)
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)

    assert await _set_app_allowed(hass, device_id, return_response=False) is None
    mock_nintendo_app.set_safe_launch_setting.assert_awaited_once()


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_unknown_application(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Test an application ID not on the console is refused before refreshing."""
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)

    with pytest.raises(ServiceValidationError) as err:
        await _set_app_allowed(hass, device_id, application_id="0100000000000000")

    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "application_not_found"
    assert err.value.translation_placeholders == {"application_id": "0100000000000000"}
    mock_nintendo_device.update.assert_not_called()


@pytest.mark.parametrize(
    ("side_effect", "error", "translation_key"),
    [
        pytest.param(
            LookupError("Application no longer in the allow list"),
            ServiceValidationError,
            "application_not_found",
            id="no_longer_on_console",
        ),
        pytest.param(
            ValueError("Settings not loaded"),
            HomeAssistantError,
            "allow_list_unavailable",
            id="settings_not_loaded",
        ),
        pytest.param(
            HttpException(status_code=500, message="Internal error"),
            HomeAssistantError,
            "allow_list_update_failed",
            id="http_error",
        ),
    ],
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_write_errors(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_app: MagicMock,
    side_effect: Exception,
    error: type[HomeAssistantError],
    translation_key: str,
) -> None:
    """Test errors while writing the setting are translated."""
    mock_nintendo_app.set_safe_launch_setting.side_effect = side_effect
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)

    with pytest.raises(error) as err:
        await _set_app_allowed(hass, device_id)

    assert type(err.value) is error
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == translation_key


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_refresh_error(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    mock_nintendo_app: MagicMock,
) -> None:
    """Test nothing is written if the device cannot be refreshed first."""
    device_id = await _console_device_id(hass, device_registry, mock_config_entry)
    mock_nintendo_device.update.side_effect = HttpException(
        status_code=500, message="Internal error"
    )

    with pytest.raises(HomeAssistantError) as err:
        await _set_app_allowed(hass, device_id)

    assert err.value.translation_key == "allow_list_update_failed"
    mock_nintendo_app.set_safe_launch_setting.assert_not_called()
