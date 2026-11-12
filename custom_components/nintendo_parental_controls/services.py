"""Services for Nintendo Parental integration."""

from enum import StrEnum
import logging

import probatio
from pynintendoparental.application import Application
from pynintendoparental.const import DAYS_OF_WEEK
from pynintendoparental.device import Device
from pynintendoparental.enum import SafeLaunchSetting
from pynintendoparental.exceptions import (
    BedtimeOutOfRangeError,
    ExtraPlayingTimeActiveError,
    InvalidDeviceStateError,
)
from pynintendoparental.player import Player

from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID, CONF_PIN
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    entity_registry as er,
    service,
)
from homeassistant.util.json import JsonValueType

from .const import (
    ATTR_ALLOWED,
    ATTR_APPLICATION_ID,
    ATTR_BEDTIME_END,
    ATTR_BEDTIME_START,
    ATTR_BONUS_TIME,
    ATTR_DAY_OF_WEEK,
    ATTR_KEY_BY_PLAYER_ID,
    ATTR_MAX_PLAY_TIME,
    BEDTIME_ALARM_DISABLE,
    BEDTIME_ALARM_MAX,
    BEDTIME_ALARM_MIN,
    BEDTIME_END_TIME_MAX,
    BEDTIME_END_TIME_MIN,
    DOMAIN,
)
from .coordinator import NintendoParentalControlsConfigEntry
from .sensor import NintendoParentalControlsSensor
from .util import handle_device_errors

_LOGGER = logging.getLogger(__name__)


class NintendoParentalService(StrEnum):
    """Store keys for Nintendo Parental services."""

    ADD_BONUS_TIME = "add_bonus_time"
    UPDATE_PIN_CODE = "update_pin_code"
    PLAYER_USAGE_REPORT = "player_usage_report"
    DEVICE_USAGE_REPORT = "device_usage_report"
    UPDATE_DAILY_RESTRICTIONS = "update_daily_restrictions"
    LIST_APPLICATIONS = "list_applications"
    SET_APP_ALLOWED = "set_app_allowed"


@callback
def async_setup_services(
    hass: HomeAssistant,
):
    """Set up the Nintendo Parental services."""
    hass.services.async_register(
        domain=DOMAIN,
        service=NintendoParentalService.ADD_BONUS_TIME,
        service_func=async_add_bonus_time,
        schema=probatio.Schema(
            {
                probatio.Required(ATTR_DEVICE_ID): cv.string,
                probatio.Required(ATTR_BONUS_TIME): probatio.All(
                    int, probatio.Range(min=5, max=30)
                ),
            }
        ),
    )
    hass.services.async_register(
        domain=DOMAIN,
        service=NintendoParentalService.PLAYER_USAGE_REPORT,
        service_func=async_get_player_usage,
        supports_response=SupportsResponse.ONLY,
        schema=probatio.Schema(
            {
                probatio.Required(ATTR_DEVICE_ID): cv.string,
                probatio.Required(ATTR_ENTITY_ID): cv.string,
            }
        ),
    )
    hass.services.async_register(
        domain=DOMAIN,
        service=NintendoParentalService.DEVICE_USAGE_REPORT,
        service_func=async_get_device_usage_report,
        supports_response=SupportsResponse.ONLY,
        schema=probatio.Schema(
            {
                probatio.Required(ATTR_DEVICE_ID): cv.string,
                probatio.Optional(ATTR_KEY_BY_PLAYER_ID, default=False): cv.boolean,
            }
        ),
    )
    service.async_register_admin_service(
        hass,
        DOMAIN,
        NintendoParentalService.UPDATE_DAILY_RESTRICTIONS,
        async_set_per_day_controls,
        probatio.Schema(
            {
                probatio.Required(ATTR_DEVICE_ID): cv.string,
                probatio.Required(ATTR_DAY_OF_WEEK): probatio.In(DAYS_OF_WEEK),
                probatio.Inclusive(ATTR_BEDTIME_START, "bedtime"): cv.time,
                probatio.Inclusive(ATTR_BEDTIME_END, "bedtime"): cv.time,
                probatio.Optional(ATTR_MAX_PLAY_TIME): probatio.All(
                    int, probatio.Range(min=0, max=360)
                ),
            }
        ),
    )
    hass.services.async_register(
        domain=DOMAIN,
        service=NintendoParentalService.LIST_APPLICATIONS,
        service_func=async_list_applications,
        supports_response=SupportsResponse.ONLY,
        schema=probatio.Schema(
            {
                probatio.Required(ATTR_DEVICE_ID): cv.string,
            }
        ),
    )
    # Admin only: the allow list lets games past the console's age rating
    # restriction.
    service.async_register_admin_service(
        hass,
        DOMAIN,
        NintendoParentalService.SET_APP_ALLOWED,
        async_set_app_allowed,
        probatio.Schema(
            {
                probatio.Required(ATTR_DEVICE_ID): cv.string,
                probatio.Required(ATTR_APPLICATION_ID): cv.string,
                probatio.Required(ATTR_ALLOWED): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    service.async_register_admin_service(
        hass,
        DOMAIN,
        NintendoParentalService.UPDATE_PIN_CODE,
        async_update_pin_code,
        probatio.Schema(
            {
                probatio.Required(ATTR_DEVICE_ID): cv.string,
                probatio.Required(probatio.Secret(CONF_PIN)): cv.string,
            }
        ),
    )


def _get_nintendo_device(hass: HomeAssistant, device_id: str) -> Device:
    """Get the Nintendo device from a device ID."""
    return _get_nintendo_device_and_entry(hass, device_id)[0]


def _get_nintendo_device_and_entry(
    hass: HomeAssistant, device_id: str
) -> tuple[Device, NintendoParentalControlsConfigEntry]:
    """Get the Nintendo device and its config entry from a device ID."""
    config_entry: NintendoParentalControlsConfigEntry
    device, config_entry = service.async_get_device_and_config_entry(
        hass, DOMAIN, device_id
    )
    nintendo_device_id = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            nintendo_device_id = identifier[1].split("_")[-1]
            break
    if (
        nintendo_device_id
        and nintendo_device_id in config_entry.runtime_data.api.devices
    ):
        return (
            config_entry.runtime_data.api.devices[nintendo_device_id],
            config_entry,
        )
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="invalid_device",
    )


def _get_nintendo_player(hass: HomeAssistant, device: Device, entity_id: str) -> Player:
    """Return a given player for a given device."""
    prefix = f"{device.device_id}_"
    suffix = f"_{NintendoParentalControlsSensor.PLAYER_PLAYING_TIME}"
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.platform != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="invalid_entity"
        )
    if entry.unique_id.startswith(prefix) and entry.unique_id.endswith(suffix):
        player_id = entry.unique_id[len(prefix) : -len(suffix)]
        if player_id in device.players:
            return device.players.get_player(player_id)
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="invalid_player"
    )


def _build_player_app_report(player: Player) -> list[dict[str, JsonValueType]]:
    """Produce a player application report."""
    return [
        {
            "playing_time": app.playing_time,
            "name": app.application.name,
            "image": app.application.image_url,
            "whitelisted": app.application.safe_launch_setting
            == SafeLaunchSetting.ALLOW,
        }
        for app in player.apps
    ]


def _application_info(application: Application) -> dict[str, JsonValueType]:
    """Describe an application and its allow list state."""
    return {
        "application_id": application.application_id,
        "name": application.name,
        "allowed": application.safe_launch_setting == SafeLaunchSetting.ALLOW,
    }


def _get_application(device: Device, application_id: str) -> Application:
    """Return an application on a device by its ID, ignoring case."""
    for application in device.applications:
        if application.application_id.casefold() == application_id.casefold():
            return application
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="application_not_found",
        translation_placeholders={"application_id": application_id},
    )


async def async_add_bonus_time(call: ServiceCall) -> None:
    """Add bonus time to a device."""
    data = call.data
    device_id: str = data[ATTR_DEVICE_ID]
    bonus_time: int = data[ATTR_BONUS_TIME]
    device = _get_nintendo_device(call.hass, device_id)
    with handle_device_errors():
        await device.add_extra_time(bonus_time)


async def async_update_pin_code(call: ServiceCall) -> None:
    """Update the PIN code for a device."""
    data = call.data
    device_id: str = data[ATTR_DEVICE_ID]
    new_pin: str = data[CONF_PIN]
    if not new_pin.isdigit() or len(new_pin) < 4 or len(new_pin) > 8:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_pin_length",
        )
    device = _get_nintendo_device(call.hass, device_id)
    with handle_device_errors():
        await device.set_new_pin(new_pin)


async def async_get_player_usage(call: ServiceCall) -> dict:
    """Get player usage."""
    data = call.data
    device_id: str = data[ATTR_DEVICE_ID]
    entity_id: str = data[ATTR_ENTITY_ID]
    device = _get_nintendo_device(call.hass, device_id)
    player = _get_nintendo_player(call.hass, device, entity_id)
    return {"apps": _build_player_app_report(player)}


async def async_get_device_usage_report(call: ServiceCall) -> dict:
    """Return the device usage report."""
    data = call.data
    device_id: str = data[ATTR_DEVICE_ID]
    device = _get_nintendo_device(call.hass, device_id)
    if data[ATTR_KEY_BY_PLAYER_ID]:
        return {
            player.player_id: {
                "nickname": player.nickname,
                "apps": _build_player_app_report(player),
            }
            for player in device.players
        }
    # Keyed by nickname for backward compatibility; players with the same
    # nickname overwrite each other.
    return {
        player.nickname: _build_player_app_report(player) for player in device.players
    }


async def async_set_per_day_controls(call: ServiceCall) -> None:
    """Set per-day restrictions for a given device."""
    data = call.data
    device_id: str = data[ATTR_DEVICE_ID]
    device = _get_nintendo_device(call.hass, device_id)
    restriction_enabled = data.get(ATTR_MAX_PLAY_TIME) is not None
    bedtime_enabled = (
        data.get(ATTR_BEDTIME_START) and data.get(ATTR_BEDTIME_END)
    ) is not None
    with handle_device_errors():
        try:
            await device.set_daily_restrictions(
                enabled=restriction_enabled,
                bedtime_enabled=bedtime_enabled,
                day_of_week=data[ATTR_DAY_OF_WEEK],
                bedtime_start=data.get(ATTR_BEDTIME_END),
                bedtime_end=data.get(ATTR_BEDTIME_START),
                max_daily_playtime=data.get(ATTR_MAX_PLAY_TIME),
            )
        except InvalidDeviceStateError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="requires_daily_restrictions",
            ) from err
        except ExtraPlayingTimeActiveError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="extra_playing_time_active",
            ) from err
        except BedtimeOutOfRangeError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="bedtime_out_of_range",
                translation_placeholders={
                    "bedtime_alarm_min": BEDTIME_ALARM_MIN,
                    "bedtime_alarm_max": BEDTIME_ALARM_MAX,
                    "bedtime_end_time_min": BEDTIME_END_TIME_MIN,
                    "bedtime_end_time_max": BEDTIME_END_TIME_MAX,
                    "bedtime_alarm_disable": BEDTIME_ALARM_DISABLE,
                },
            ) from err


async def async_list_applications(call: ServiceCall) -> ServiceResponse:
    """Return the applications on a device and whether they are allowed.

    Uses the state from the last poll.
    """
    device = _get_nintendo_device(call.hass, call.data[ATTR_DEVICE_ID])
    return {
        "applications": [
            {
                **_application_info(application),
                "image": application.image_url,
            }
            for application in device.applications
        ]
    }


async def async_set_app_allowed(call: ServiceCall) -> ServiceResponse:
    """Add an application to, or remove it from, a device's allow list.

    The library sends the device's whole restriction settings back to
    Nintendo, so the device is refreshed first; otherwise a change made in
    Nintendo's app since the last poll could be overwritten. Nothing is sent
    if the application already has the requested state.
    """
    data = call.data
    allowed: bool = data[ATTR_ALLOWED]
    device, config_entry = _get_nintendo_device_and_entry(
        call.hass, data[ATTR_DEVICE_ID]
    )
    application = _get_application(device, data[ATTR_APPLICATION_ID])
    setting = SafeLaunchSetting.ALLOW if allowed else SafeLaunchSetting.NONE
    with handle_device_errors():
        await device.update()
        changed = application.safe_launch_setting != setting
        if changed:
            try:
                await application.set_safe_launch_setting(setting)
            except LookupError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="application_not_found",
                    translation_placeholders={
                        "application_id": application.application_id
                    },
                ) from err
            except ValueError as err:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="allow_list_unavailable",
                ) from err
    # The library parsed the settings Nintendo returned; show the refreshed
    # device data in the entities.
    config_entry.runtime_data.async_update_listeners()
    return {**_application_info(application), "changed": changed}
