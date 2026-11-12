"""Test the add_bonus_time action range and selector."""

from pathlib import Path
from unittest.mock import AsyncMock

import probatio
import pytest
from pytest_homeassistant.common import MockConfigEntry
import yaml

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import setup_integration
from custom_components.nintendo_parental_controls.const import ATTR_BONUS_TIME, DOMAIN
from custom_components.nintendo_parental_controls.services import (
    NintendoParentalService,
)

SERVICES_YAML = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / DOMAIN
    / "services.yaml"
)


def test_bonus_time_selector_matches_schema() -> None:
    """The add_bonus_time selector allows the same range as the schema."""
    services = yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))
    selector = services["add_bonus_time"]["fields"]["bonus_time"]["selector"]
    assert selector["number"]["min"] == -1
    assert selector["number"]["max"] == 360


@pytest.mark.parametrize(
    ("bonus_time", "valid"),
    [(-2, False), (-1, True), (5, True), (360, True), (361, False)],
)
@pytest.mark.usefixtures("mock_nintendo_client")
async def test_bonus_time_schema_range(
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_device: AsyncMock,
    bonus_time: int,
    valid: bool,
) -> None:
    """The add_bonus_time schema accepts -1 to 360 minutes."""
    await setup_integration(hass, mock_config_entry)
    device_entry = device_registry.async_get_device_by_identifier(
        (DOMAIN, "testdevid"), mock_config_entry.entry_id
    )
    assert device_entry
    call = hass.services.async_call(
        DOMAIN,
        NintendoParentalService.ADD_BONUS_TIME,
        {ATTR_DEVICE_ID: device_entry.id, ATTR_BONUS_TIME: bonus_time},
        blocking=True,
    )
    if valid:
        await call
        mock_nintendo_device.add_extra_time.assert_called_once_with(bonus_time)
    else:
        with pytest.raises(probatio.Invalid):
            await call
        mock_nintendo_device.add_extra_time.assert_not_called()
