"""Nintendo parental controls data coordinator."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from http import HTTPStatus
import logging
from typing import override

from aiohttp import ClientError
from pynintendoauth.exceptions import (
    HttpException,
    InvalidOAuthConfigurationException,
    InvalidSessionTokenException,
)
from pynintendoparental import Authenticator, NintendoParental
from pynintendoparental.exceptions import NoDevicesFoundException

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_PLAYING_HOLDOVER, DEFAULT_PLAYING_HOLDOVER, DOMAIN

type NintendoParentalControlsConfigEntry = ConfigEntry[NintendoUpdateCoordinator]

_LOGGER = logging.getLogger(__name__)
UPDATE_INTERVAL = timedelta(seconds=60)


@dataclass
class PlayActivity:
    """Play time growth observed between polls.

    Nintendo does not publish a "now playing" signal. The console uploads its
    play time every few minutes, so play is inferred from that total growing.
    """

    playing_time: int | float | None = None
    last_increase: datetime | None = None

    def observe(self, playing_time: int | float | None, now: datetime) -> None:
        """Record a new play time total."""
        if playing_time is None:
            return
        if self.playing_time is not None and playing_time > self.playing_time:
            self.last_increase = now
        self.playing_time = playing_time


class NintendoUpdateCoordinator(DataUpdateCoordinator[None]):
    """Nintendo data update coordinator."""

    config_entry: NintendoParentalControlsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        authenticator: Authenticator,
        config_entry: NintendoParentalControlsConfigEntry,
    ) -> None:
        """Initialize update coordinator."""
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=config_entry,
        )
        self.authenticator = authenticator
        self.api = NintendoParental(
            authenticator, hass.config.time_zone, hass.config.language
        )
        self.play_activity: dict[tuple[str, str | None], PlayActivity] = {}
        self.device_last_update: dict[str, datetime] = {}
        self._watched_devices: set[str] = set()
        self._failed_devices: set[str] = set()

    def device_available(self, device_id: str) -> bool:
        """Return if the last poll updated this device."""
        return device_id not in self._failed_devices

    def _record_device_update(self, device_id: str) -> None:
        """Record that the library finished updating a device."""
        self.device_last_update[device_id] = dt_util.utcnow()

    def _watch_devices(self) -> None:
        """Get notified when the library finishes updating a device.

        The library logs and swallows errors raised while updating a single
        device, leaving its previous data in place. It only runs device
        callbacks at the end of a successful update, so they tell which
        devices are current.
        """
        for device in self.api.devices.values():
            if device.device_id not in self._watched_devices:
                self._watched_devices.add(device.device_id)
                device.add_device_callback(
                    partial(self._record_device_update, device.device_id)
                )

    def _check_device_updates(self, started: datetime) -> None:
        """Mark devices the library failed to update in this poll."""
        failed = {
            device_id
            for device_id in self._watched_devices
            if (last_update := self.device_last_update.get(device_id)) is None
            or last_update < started
        }
        for device_id in failed - self._failed_devices:
            _LOGGER.warning(
                "Updating Nintendo device %s failed, marking it unavailable", device_id
            )
        for device_id in self._failed_devices - failed:
            _LOGGER.info("Nintendo device %s is available again", device_id)
        self._failed_devices = failed

    @property
    def playing_holdover(self) -> timedelta:
        """Return how long play is assumed to continue after play time grew."""
        return timedelta(
            minutes=self.config_entry.options.get(
                CONF_PLAYING_HOLDOVER, DEFAULT_PLAYING_HOLDOVER
            )
        )

    def get_play_activity(
        self, device_id: str, player_id: str | None = None
    ) -> PlayActivity:
        """Return the play activity of a device, or of a player on it."""
        return self.play_activity.setdefault((device_id, player_id), PlayActivity())

    def is_playing(self, device_id: str, player_id: str | None = None) -> bool:
        """Return if play time grew within the hold-over period."""
        last_increase = self.get_play_activity(device_id, player_id).last_increase
        return (
            last_increase is not None
            and dt_util.utcnow() - last_increase < self.playing_holdover
        )

    def _track_play_activity(self) -> None:
        """Compare play time totals with the previous poll."""
        now = dt_util.utcnow()
        for device in self.api.devices.values():
            if not self.device_available(device.device_id):
                continue
            self.get_play_activity(device.device_id).observe(
                device.today_playing_time, now
            )
            for player in device.players:
                self.get_play_activity(device.device_id, player.player_id).observe(
                    player.playing_time, now
                )

    async def _async_validate_session_token(self) -> None:
        """Log in again with the stored session token.

        Nintendo sometimes rejects a valid access token (HTTP 401
        invalid_token), so a rejection alone is not proof that the session
        token was revoked. Raise ConfigEntryAuthFailed only if a fresh login
        with the session token is refused too.
        """
        try:
            await self.authenticator.async_complete_login(use_session_token=True)
        except (
            InvalidSessionTokenException,
            InvalidOAuthConfigurationException,
        ) as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_expired",
            ) from err
        except (HttpException, ClientError, TimeoutError) as err:
            _LOGGER.debug("Could not validate the session token: %s", err)

    @override
    async def _async_update_data(self) -> None:
        """Update data from Nintendo's API."""
        started = dt_util.utcnow()
        try:
            await self.api.update()
        except InvalidOAuthConfigurationException as err:
            # pylint: disable-next=home-assistant-exception-translation-key-missing
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except NoDevicesFoundException as err:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="no_devices_found",
            ) from err
        except InvalidSessionTokenException as err:
            await self._async_validate_session_token()
            _LOGGER.debug("Session token invalid, will renew on next update")
            raise UpdateFailed from err
        except HttpException as err:
            if err.error_code == "update_required":
                raise ConfigEntryError(
                    translation_domain=DOMAIN,
                    translation_key="update_required",
                ) from err
            if err.status_code == HTTPStatus.UNAUTHORIZED:
                await self._async_validate_session_token()
                raise UpdateFailed from err
            raise UpdateFailed(retry_after=900) from err
        self._check_device_updates(started)
        # Devices found in this poll are watched from the next one on.
        self._watch_devices()
        self._track_play_activity()
