"""Utilities for Nintendo parental controls."""

from collections.abc import Generator
from contextlib import contextmanager

from aiohttp import ClientError
from pynintendoauth.exceptions import HttpException
from pynintendoparental.exceptions import (
    BedtimeOutOfRangeError,
    DailyPlaytimeOutOfRangeError,
    DeviceError,
    ExtraPlayingTimeActiveError,
    InputValidationError,
    InvalidDeviceStateError,
)

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import (
    BEDTIME_ALARM_DISABLE,
    BEDTIME_ALARM_MAX,
    BEDTIME_ALARM_MIN,
    BEDTIME_END_TIME_MAX,
    BEDTIME_END_TIME_MIN,
    DOMAIN,
)


@contextmanager
def handle_device_errors() -> Generator[None]:
    """Raise translated errors for library errors raised by a device action."""
    try:
        yield
    except ExtraPlayingTimeActiveError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="extra_playing_time_active_settings",
        ) from err
    except InvalidDeviceStateError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_device_state",
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
    except DailyPlaytimeOutOfRangeError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="daily_playtime_out_of_range",
            translation_placeholders={"value": str(err.value)},
        ) from err
    except InputValidationError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_value",
            translation_placeholders={"value": str(err.value)},
        ) from err
    except DeviceError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="device_error",
            translation_placeholders={"error": err.message},
        ) from err
    except (HttpException, ClientError, TimeoutError) as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="communication_error",
            translation_placeholders={"error": str(err)},
        ) from err
