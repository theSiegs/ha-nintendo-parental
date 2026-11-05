"""Test diagnostics."""

from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant.components.diagnostics import get_diagnostics_for_config_entry
from pytest_homeassistant.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion

from homeassistant.core import HomeAssistant

from . import setup_integration


@pytest.mark.freeze_time("2026-11-05 18:00:00+00:00")
async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_device: AsyncMock,
    freezer: FrozenDateTimeFactory,
    snapshot: SnapshotAssertion,
) -> None:
    """Test diagnostics are returned with personal data redacted."""
    # Attributes the library sets in Device.__init__ are not on the spec.
    mock_nintendo_device.last_sync = 1793944800
    mock_nintendo_device.stats_update_failed = False
    mock_nintendo_device.alarms_enabled = True
    mock_nintendo_device.parental_control_settings = {
        "playTimerRegulations": {"timerMode": "DAILY", "restrictionMode": "ALARM"},
        "unlockCode": "1234",
    }
    await setup_integration(hass, mock_config_entry)
    mock_nintendo_device.today_playing_time = 115
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )
    assert diagnostics == snapshot

    text = str(diagnostics)
    for secret in ("valid_token", "SN12345678", "HA Gamer", "Home Assistant Test"):
        assert secret not in text
    assert "1234" not in text
