"""Test listing applications and changing the allow list."""

from unittest.mock import AsyncMock, MagicMock

from pynintendoauth.exceptions import HttpException
from pynintendoparental.application import Application
from pynintendoparental.enum import SafeLaunchSetting
from pynintendoparental.exceptions import DeviceError
import pytest
from pytest_homeassistant.common import MockConfigEntry, MockUser

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from homeassistant.helpers import device_registry as dr

from . import setup_integration
from custom_components.nintendo_parental_controls.const import (
    ATTR_ALLOWED,
    ATTR_APPLICATION_ID,
    DOMAIN,
)
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


def _write_setting(app: Application) -> None:
    """Make the mocked write change the application, like the library does."""

    async def set_safe_launch_setting(setting: SafeLaunchSetting) -> None:
        app.safe_launch_setting = setting

    app.set_safe_launch_setting.side_effect = set_safe_launch_setting


async def _set_app_allowed(
    hass: HomeAssistant,
    device_id: str,
    application_id: str = "testappid",
    allowed: bool = False,
    return_response: bool = True,
) -> dict | None:
    """Call the set_app_allowed action."""
    return await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.SET_APP_ALLOWED,
        {
            ATTR_DEVICE_ID: device_id,
            ATTR_APPLICATION_ID: application_id,
            ATTR_ALLOWED: allowed,
        },
        blocking=True,
        return_response=return_response,
    )


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_list_applications(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """Applications are listed with their ID and allow list state."""
    other = MagicMock(spec=Application)
    other.application_id = "otherappid"
    other.name = "Some Game"
    other.image_url = None
    other.safe_launch_setting = SafeLaunchSetting.NONE
    mock_nintendo_device.applications.add_application(other)
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    response = await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.LIST_APPLICATIONS,
        {ATTR_DEVICE_ID: device_id},
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
                "name": "Some Game",
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
    """The device is refreshed, then the application's setting is written."""
    mock_nintendo_app.safe_launch_setting = initial
    _write_setting(mock_nintendo_app)
    device_id = await _device_id(hass, device_registry, mock_config_entry)
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
    """Application IDs match regardless of case."""
    _write_setting(mock_nintendo_app)
    device_id = await _device_id(hass, device_registry, mock_config_entry)

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
    """Nothing is written if the application already has the state."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    response = await _set_app_allowed(hass, device_id, allowed=True)

    mock_nintendo_device.update.assert_awaited_once_with()
    mock_nintendo_app.set_safe_launch_setting.assert_not_called()
    assert response == {
        "application_id": "testappid",
        "name": "Test Game Name",
        "allowed": True,
        "changed": False,
    }


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_uses_refreshed_state(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    mock_nintendo_app: MagicMock,
) -> None:
    """A change made elsewhere since the last poll is seen before writing."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)

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
    """The response is optional."""
    _write_setting(mock_nintendo_app)
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    assert await _set_app_allowed(hass, device_id, return_response=False) is None
    mock_nintendo_app.set_safe_launch_setting.assert_awaited_once()


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_unknown_application(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
) -> None:
    """An application ID not on the console is refused before refreshing."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    with pytest.raises(ServiceValidationError) as err:
        await _set_app_allowed(hass, device_id, application_id="0100000000000000")

    assert err.value.translation_key == "application_not_found"
    assert err.value.translation_placeholders == {"application_id": "0100000000000000"}
    mock_nintendo_device.update.assert_not_called()


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_invalid_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """An unknown device is refused."""
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(ServiceValidationError) as err:
        await _set_app_allowed(hass, "invalid_device")

    assert err.value.translation_key == "service_device_not_found"


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_set_app_allowed_requires_admin(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_app: MagicMock,
    hass_read_only_user: MockUser,
) -> None:
    """Only administrators can change the allow list."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            NintendoParentalService.SET_APP_ALLOWED,
            {
                ATTR_DEVICE_ID: device_id,
                ATTR_APPLICATION_ID: "testappid",
                ATTR_ALLOWED: False,
            },
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )

    mock_nintendo_app.set_safe_launch_setting.assert_not_called()


@pytest.mark.parametrize(
    ("side_effect", "error", "translation_key"),
    [
        pytest.param(
            LookupError("no longer in whitelist"),
            ServiceValidationError,
            "application_not_found",
            id="no_longer_on_console",
        ),
        pytest.param(
            ValueError("callbacks not executed"),
            HomeAssistantError,
            "allow_list_unavailable",
            id="settings_not_loaded",
        ),
        pytest.param(
            DeviceError("refused"),
            HomeAssistantError,
            "device_error",
            id="device_error",
        ),
        pytest.param(
            HttpException(500, "Internal error"),
            HomeAssistantError,
            "communication_error",
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
    """Errors while writing the setting are translated."""
    mock_nintendo_app.set_safe_launch_setting.side_effect = side_effect
    device_id = await _device_id(hass, device_registry, mock_config_entry)

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
    """Nothing is written if the device cannot be refreshed first."""
    device_id = await _device_id(hass, device_registry, mock_config_entry)
    mock_nintendo_device.update.side_effect = HttpException(500, "Internal error")

    with pytest.raises(HomeAssistantError) as err:
        await _set_app_allowed(hass, device_id)

    assert err.value.translation_key == "communication_error"
    mock_nintendo_app.set_safe_launch_setting.assert_not_called()
