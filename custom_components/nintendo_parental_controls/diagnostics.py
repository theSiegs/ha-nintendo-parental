"""Diagnostics support for Nintendo parental controls."""

from datetime import time
from typing import Any

from pynintendoparental.device import Device

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_SESSION_TOKEN
from .coordinator import NintendoParentalControlsConfigEntry, NintendoUpdateCoordinator

TO_REDACT = {
    CONF_SESSION_TOKEN,
    "name",
    "nickname",
    "player_image",
    "serial_number",
}


def _isoformat(value: time | None) -> str | None:
    """Return a time as an ISO 8601 string."""
    return value.isoformat() if value is not None else None


def _device_diagnostics(
    coordinator: NintendoUpdateCoordinator, device: Device
) -> dict[str, Any]:
    """Return diagnostics for a single console."""
    activity = coordinator.get_play_activity(device.device_id)
    return {
        "device_id": device.device_id,
        "name": device.name,
        "model": device.model,
        "generation": device.generation,
        "firmware_version": device.extra.get("firmwareVersion", {}).get(
            "displayedVersion"
        ),
        "serial_number": device.extra.get("serialNumber"),
        "last_sync": device.last_sync,
        "available": coordinator.device_available(device.device_id),
        "last_update": coordinator.device_last_update.get(device.device_id),
        "stats_update_failed": device.stats_update_failed,
        "timer_mode": device.timer_mode,
        "limit_time": device.limit_time,
        "extra_playing_time": device.extra_playing_time,
        "today_playing_time": device.today_playing_time,
        "today_time_remaining": device.today_time_remaining,
        "bedtime_alarm": _isoformat(device.bedtime_alarm),
        "bedtime_end": _isoformat(device.bedtime_end),
        "forced_termination_mode": device.forced_termination_mode,
        "alarms_enabled": device.alarms_enabled,
        "playing": coordinator.is_playing(device.device_id),
        "last_increase": activity.last_increase,
        "applications": len(device.applications),
        "play_timer_regulations": device.parental_control_settings.get(
            "playTimerRegulations"
        ),
        "players": [
            {
                "player_id": player.player_id,
                "nickname": player.nickname,
                "player_image": player.player_image,
                "playing_time": player.playing_time,
                "apps_played_today": len(player.apps),
                "playing": coordinator.is_playing(device.device_id, player.player_id),
                "last_increase": coordinator.get_play_activity(
                    device.device_id, player.player_id
                ).last_increase,
            }
            for player in device.players
        ],
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NintendoParentalControlsConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "devices": [
            async_redact_data(_device_diagnostics(coordinator, device), TO_REDACT)
            for device in coordinator.api.devices.values()
        ],
    }
