"""Test entities are added for consoles and players that appear after setup."""

from datetime import time
from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from pynintendoparental.application import ApplicationRegistry
from pynintendoparental.device import Device
from pynintendoparental.enum import DeviceTimerMode
from pynintendoparental.player import Player, PlayerRegistry
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import setup_integration
from custom_components.nintendo_parental_controls.const import DOMAIN


def _player(player_id: str, nickname: str) -> Player:
    player = MagicMock(spec=Player)
    player.player_id = player_id
    player.nickname = nickname
    player.apps = []
    player.playing_time = 0
    player.player_image = None
    return player


def _device(device_id: str, name: str) -> Device:
    players = PlayerRegistry()
    device = AsyncMock(spec=Device)
    device.device_id = device_id
    device.name = name
    device.extra = {
        "firmwareVersion": {"displayedVersion": "20.0.0"},
        "serialNumber": "SN00000002",
    }
    device.limit_time = 60
    device.today_playing_time = 0
    device.today_time_remaining = 60
    device.bedtime_end = time(hour=7)
    device.bedtime_alarm = time(hour=20)
    device.timer_mode = DeviceTimerMode.DAILY
    device.extra_playing_time = None
    device.forced_termination_mode = False
    device.model = "Switch 2"
    device.generation = "P01"
    device.applications = ApplicationRegistry()
    device.players = players
    device.get_player = MagicMock(side_effect=players.get_player)
    return device


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _unique_ids(entity_registry: er.EntityRegistry, entry: MockConfigEntry) -> set:
    return {
        entity.unique_id
        for entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    }


async def test_new_player_adds_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A player that appears after setup gets its entities without a reload."""
    await setup_integration(hass, mock_config_entry)
    before = _unique_ids(entity_registry, mock_config_entry)
    assert "testdevid_newplayer_player_playing_time" not in before

    mock_nintendo_device.players.add_player(_player("newplayer", "Sam"))
    await _poll(hass, freezer)

    added = _unique_ids(entity_registry, mock_config_entry) - before
    assert added == {
        "testdevid_newplayer_player_playing_time",
        "testdevid_newplayer_playing",
    }
    assert hass.states.get("sensor.home_assistant_test_sam_used_screen_time")

    # Nothing is added twice on later polls.
    await _poll(hass, freezer)
    assert _unique_ids(entity_registry, mock_config_entry) == before | added


async def test_new_device_adds_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A console paired after setup gets its device and entities."""
    await setup_integration(hass, mock_config_entry)
    before = _unique_ids(entity_registry, mock_config_entry)

    new_device = _device("newdevid", "The Switch")
    new_device.players.add_player(_player("alexid", "Alex"))
    mock_nintendo_client.devices["newdevid"] = new_device
    await _poll(hass, freezer)

    assert device_registry.async_get_device_by_identifier(
        (DOMAIN, "newdevid"), mock_config_entry.entry_id
    )
    added = _unique_ids(entity_registry, mock_config_entry) - before
    assert added == {
        "newdevid_playing",
        "newdevid_today_max_screentime",
        "newdevid_timer_mode",
        "newdevid_playing_time",
        "newdevid_time_remaining",
        "newdevid_time_extended",
        "newdevid_suspend_software",
        "newdevid_bedtime_alarm",
        "newdevid_bedtime_end_time",
        "newdevid_alexid_player_playing_time",
        "newdevid_alexid_playing",
    }
    assert hass.states.get("sensor.the_switch_alex_used_screen_time").state == "0"
