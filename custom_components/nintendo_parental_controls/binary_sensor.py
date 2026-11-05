"""Binary sensor platform for Nintendo parental controls."""

from datetime import datetime
from enum import StrEnum
from typing import Any, override

from pynintendoparental.device import Device
from pynintendoparental.player import Player

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_LAST_INCREASE
from .coordinator import NintendoParentalControlsConfigEntry, NintendoUpdateCoordinator
from .entity import NintendoDevice, async_setup_dynamic_entities

# Coordinator is used to centralize the data updates
PARALLEL_UPDATES = 0


class NintendoParentalControlsBinarySensor(StrEnum):
    """Store keys for Nintendo parental controls binary sensors."""

    PLAYING = "playing"
    PLAYER_PLAYING = "player_playing"


DEVICE_PLAYING_DESCRIPTION = BinarySensorEntityDescription(
    key=NintendoParentalControlsBinarySensor.PLAYING,
    translation_key=NintendoParentalControlsBinarySensor.PLAYING,
)

PLAYER_PLAYING_DESCRIPTION = BinarySensorEntityDescription(
    key=NintendoParentalControlsBinarySensor.PLAYER_PLAYING,
    translation_key=NintendoParentalControlsBinarySensor.PLAYER_PLAYING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NintendoParentalControlsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    async_setup_dynamic_entities(
        entry,
        async_add_entities,
        lambda coordinator, device: [
            NintendoDevicePlayingBinarySensor(coordinator, device)
        ],
        lambda coordinator, device, player: [
            NintendoPlayerPlayingBinarySensor(coordinator, device, player)
        ],
    )


class NintendoPlayingBinarySensor(NintendoDevice, BinarySensorEntity):
    """Base class for the inferred playing binary sensors.

    Nintendo does not report what is being played right now. Play is inferred
    from the day's play time growing between polls, and assumed to continue
    for a configurable hold-over period, because the console only uploads its
    play time every few minutes.
    """

    _unrecorded_attributes = frozenset({ATTR_LAST_INCREASE})
    _player_id: str | None = None

    @property
    @override
    def is_on(self) -> bool:
        """Return if play time grew recently."""
        return self.coordinator.is_playing(self._device.device_id, self._player_id)

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return when play time was last seen growing."""
        last_increase: datetime | None = self.coordinator.get_play_activity(
            self._device.device_id, self._player_id
        ).last_increase
        return {ATTR_LAST_INCREASE: last_increase}


class NintendoDevicePlayingBinarySensor(NintendoPlayingBinarySensor):
    """Represent whether a console is being played."""

    def __init__(self, coordinator: NintendoUpdateCoordinator, device: Device) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            coordinator=coordinator,
            device=device,
            key=DEVICE_PLAYING_DESCRIPTION.key,
        )
        self.entity_description = DEVICE_PLAYING_DESCRIPTION


class NintendoPlayerPlayingBinarySensor(NintendoPlayingBinarySensor):
    """Represent whether a player is playing on a console."""

    def __init__(
        self,
        coordinator: NintendoUpdateCoordinator,
        device: Device,
        player: Player,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            coordinator=coordinator,
            device=device,
            key=PLAYER_PLAYING_DESCRIPTION.key,
        )
        self.entity_description = PLAYER_PLAYING_DESCRIPTION
        self._player_id = player.player_id
        self._attr_translation_placeholders = {"nickname": player.nickname or ""}
        self._attr_unique_id = (
            f"{device.device_id}_{player.player_id}"
            f"_{NintendoParentalControlsBinarySensor.PLAYING}"
        )
