"""Test reauthentication is requested when Nintendo rejects the token."""

from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from pynintendoauth.exceptions import HttpException, InvalidSessionTokenException
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant

from . import setup_integration


def _invalid_grant() -> InvalidSessionTokenException:
    return InvalidSessionTokenException(400, "invalid_grant")


def _invalid_token() -> HttpException:
    return HttpException(401, "", "invalid_token")


def _reauth_flows(hass: HomeAssistant, entry: MockConfigEntry) -> list:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(entry.domain)
        if flow["context"]["source"] == SOURCE_REAUTH
        and flow["context"]["entry_id"] == entry.entry_id
    ]


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


@pytest.mark.parametrize("exception", [_invalid_grant, _invalid_token])
async def test_rejected_token_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_authenticator: MagicMock,
    freezer: FrozenDateTimeFactory,
    exception,
) -> None:
    """A token Nintendo keeps rejecting at runtime starts the reauth flow."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    mock_nintendo_client.update.side_effect = exception()
    mock_nintendo_authenticator.async_complete_login.side_effect = _invalid_grant()
    await _poll(hass, freezer)

    mock_nintendo_authenticator.async_complete_login.assert_called_with(
        use_session_token=True
    )
    assert len(_reauth_flows(hass, mock_config_entry)) == 1
    assert not mock_config_entry.runtime_data.last_update_success


@pytest.mark.parametrize("exception", [_invalid_grant, _invalid_token])
async def test_transient_token_rejection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_authenticator: MagicMock,
    freezer: FrozenDateTimeFactory,
    exception,
) -> None:
    """A rejection that a fresh login clears does not start reauth."""
    await setup_integration(hass, mock_config_entry)
    logins = mock_nintendo_authenticator.async_complete_login.call_count

    working_update = mock_nintendo_client.update.side_effect
    mock_nintendo_client.update.side_effect = exception()
    await _poll(hass, freezer)

    assert mock_nintendo_authenticator.async_complete_login.call_count == logins + 1
    assert not _reauth_flows(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert not coordinator.last_update_success

    mock_nintendo_client.update.side_effect = working_update
    await _poll(hass, freezer)
    assert coordinator.last_update_success


async def test_relogin_unreachable_does_not_start_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_authenticator: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """If the login check itself fails to connect, try again later."""
    await setup_integration(hass, mock_config_entry)

    mock_nintendo_client.update.side_effect = _invalid_token()
    mock_nintendo_authenticator.async_complete_login.side_effect = HttpException(
        503, "Service unavailable"
    )
    await _poll(hass, freezer)

    assert not _reauth_flows(hass, mock_config_entry)
    assert not mock_config_entry.runtime_data.last_update_success


async def test_rejected_token_during_first_refresh(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_authenticator: MagicMock,
) -> None:
    """A token rejected during the first refresh fails setup with reauth."""
    mock_nintendo_client.update.side_effect = _invalid_grant()
    # Setup logs in once successfully, then the session token is revoked.
    mock_nintendo_authenticator.async_complete_login.side_effect = [
        None,
        _invalid_grant(),
    ]
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    assert mock_config_entry.error_reason_translation_key == "auth_expired"
    assert len(_reauth_flows(hass, mock_config_entry)) == 1
