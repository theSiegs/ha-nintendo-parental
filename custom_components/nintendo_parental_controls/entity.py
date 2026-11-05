"""Base entity definition for Nintendo parental controls."""

from collections.abc import Callable, Iterable
from typing import override

from pynintendoparental.device import Device
from pynintendoparental.player import Player

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NintendoParentalControlsConfigEntry, NintendoUpdateCoordinator


@callback
def async_setup_dynamic_entities(
    entry: NintendoParentalControlsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    device_entities: Callable[[NintendoUpdateCoordinator, Device], Iterable[Entity]],
    player_entities: (
        Callable[[NintendoUpdateCoordinator, Device, Player], Iterable[Entity]] | None
    ) = None,
) -> None:
    """Add entities for current consoles and players, and for any added later.

    Consoles and players can appear after setup: a console paired later, a
    new player profile, or players Nintendo only starts returning once a
    monthly summary is available.
    """
    coordinator = entry.runtime_data
    known_devices: set[str] = set()
    known_players: set[tuple[str, str]] = set()

    @callback
    def _async_add_new_entities() -> None:
        entities: list[Entity] = []
        for device in coordinator.api.devices.values():
            if device.device_id not in known_devices:
                known_devices.add(device.device_id)
                entities.extend(device_entities(coordinator, device))
            if player_entities is None:
                continue
            for player in device.players:
                if (device.device_id, player.player_id) in known_players:
                    continue
                known_players.add((device.device_id, player.player_id))
                entities.extend(player_entities(coordinator, device, player))
        if entities:
            async_add_entities(entities)

    _async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


class NintendoDevice(CoordinatorEntity[NintendoUpdateCoordinator]):
    """Represent a Nintendo Switch."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: NintendoUpdateCoordinator, device: Device, key: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = f"{device.device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.device_id)},
            manufacturer="Nintendo",
            name=device.name,
            sw_version=device.extra["firmwareVersion"]["displayedVersion"],
            model=device.model,
            model_id=device.generation,
            serial_number=device.extra["serialNumber"],
        )

    @override
    async def async_added_to_hass(self) -> None:
        """When entity is loaded."""
        await super().async_added_to_hass()
        self._device.add_device_callback(self.async_write_ha_state)

    @override
    async def async_will_remove_from_hass(self) -> None:
        """When will be removed from HASS."""
        self._device.remove_device_callback(self.async_write_ha_state)
        await super().async_will_remove_from_hass()
