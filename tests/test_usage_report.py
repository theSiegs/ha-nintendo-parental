"""Test the device usage report keyed by player ID."""

from unittest.mock import AsyncMock, MagicMock

from pynintendoparental.player import Player
import pytest
from pytest_homeassistant.common import MockConfigEntry

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import setup_integration
from custom_components.nintendo_parental_controls.const import (
    ATTR_KEY_BY_PLAYER_ID,
    DOMAIN,
)
from custom_components.nintendo_parental_controls.services import (
    NintendoParentalService,
)

APP_REPORT = [
    {
        "image": "http://example.com/image.png",
        "name": "Test Game Name",
        "playing_time": 110,
        "whitelisted": True,
    }
]


@pytest.fixture
def second_player_same_nickname(mock_nintendo_device: AsyncMock) -> None:
    """Add a second player with the same nickname as the first."""
    player = MagicMock(spec=Player)
    player.player_id = "otherplayerid"
    player.nickname = "HA Gamer"
    player.apps = []
    player.playing_time = 0
    player.player_image = None
    mock_nintendo_device.players.add_player(player)


async def _report(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    entry: MockConfigEntry,
    **data,
) -> dict:
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), entry.entry_id
    )
    assert device_entry
    return await hass.services.async_call(
        DOMAIN,
        NintendoParentalService.DEVICE_USAGE_REPORT,
        {ATTR_DEVICE_ID: device_entry.id, **data},
        blocking=True,
        return_response=True,
    )


@pytest.mark.usefixtures("mock_nintendo_client")
async def test_report_keyed_by_player_id(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """The opt-in report is keyed by player ID with the nickname inside."""
    await setup_integration(hass, mock_config_entry)

    response = await _report(
        hass, device_registry, mock_config_entry, **{ATTR_KEY_BY_PLAYER_ID: True}
    )
    assert response == {
        "testplayerid": {"nickname": "HA Gamer", "apps": APP_REPORT},
    }


@pytest.mark.usefixtures("mock_nintendo_client", "second_player_same_nickname")
async def test_same_nickname(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Players with the same nickname only stay apart when keyed by player ID."""
    await setup_integration(hass, mock_config_entry)

    response = await _report(
        hass, device_registry, mock_config_entry, **{ATTR_KEY_BY_PLAYER_ID: True}
    )
    assert response == {
        "testplayerid": {"nickname": "HA Gamer", "apps": APP_REPORT},
        "otherplayerid": {"nickname": "HA Gamer", "apps": []},
    }

    # The default shape is unchanged: keyed by nickname, last player wins.
    assert await _report(hass, device_registry, mock_config_entry) == {"HA Gamer": []}
    assert await _report(
        hass, device_registry, mock_config_entry, **{ATTR_KEY_BY_PLAYER_ID: False}
    ) == {"HA Gamer": []}
