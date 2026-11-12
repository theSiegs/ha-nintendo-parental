"""Button platform for Nintendo parental controls."""

from enum import StrEnum
from typing import override

from pynintendoparental.device import Device

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NintendoParentalControlsConfigEntry, NintendoUpdateCoordinator
from .entity import NintendoDevice, async_setup_dynamic_entities
from .util import async_cancel_extra_time

PARALLEL_UPDATES = 1


class NintendoParentalButton(StrEnum):
    """Store keys for Nintendo parental controls buttons."""

    CANCEL_EXTRA_PLAYING_TIME = "cancel_extra_playing_time"


CANCEL_EXTRA_PLAYING_TIME_DESCRIPTION = ButtonEntityDescription(
    key=NintendoParentalButton.CANCEL_EXTRA_PLAYING_TIME,
    translation_key=NintendoParentalButton.CANCEL_EXTRA_PLAYING_TIME,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NintendoParentalControlsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button platform."""
    async_setup_dynamic_entities(
        entry,
        async_add_entities,
        lambda coordinator, device: [
            NintendoCancelExtraPlayingTimeButton(
                coordinator, device, CANCEL_EXTRA_PLAYING_TIME_DESCRIPTION
            )
        ],
    )


class NintendoCancelExtraPlayingTimeButton(NintendoDevice, ButtonEntity):
    """Cancel today's extra playing time on a console."""

    def __init__(
        self,
        coordinator: NintendoUpdateCoordinator,
        device: Device,
        description: ButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator=coordinator, device=device, key=description.key)
        self.entity_description = description

    @override
    async def async_press(self) -> None:
        """Cancel the extra playing time, or say that none is active."""
        if await async_cancel_extra_time(self._device) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_extra_playing_time",
            )
