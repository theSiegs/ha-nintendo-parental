"""Tests for the Nintendo Switch parental controls integration."""

from pytest_homeassistant.common import MockConfigEntry

import homeassistant.const as ha_const
from homeassistant.core import HomeAssistant

from custom_components.nintendo_parental_controls.compat import CommonServiceArgument

# Fork only: core's tests import CommonServiceArgument from homeassistant.const,
# which Home Assistant 2026.11 does not have yet.
if not hasattr(ha_const, "CommonServiceArgument"):
    ha_const.CommonServiceArgument = CommonServiceArgument  # type: ignore[attr-defined]


async def setup_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Set up the integration for testing platforms."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
