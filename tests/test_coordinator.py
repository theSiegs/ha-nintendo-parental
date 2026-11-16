"""Test coordinator error handling."""

from unittest.mock import AsyncMock, MagicMock

from freezegun.api import FrozenDateTimeFactory
from pynintendoauth.exceptions import (
    HttpException,
    InvalidOAuthConfigurationException,
    InvalidSessionTokenException,
)
from pynintendoparental.exceptions import NoDevicesFoundException
import pytest
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration


@pytest.mark.parametrize(
    ("exception", "translation_key", "expected_state", "expected_log_message"),
    [
        (
            InvalidOAuthConfigurationException(
                status_code=401, message="Authentication failed"
            ),
            "invalid_auth",
            ConfigEntryState.SETUP_ERROR,
            None,
        ),
        (
            NoDevicesFoundException(),
            "no_devices_found",
            ConfigEntryState.SETUP_ERROR,
            None,
        ),
        (
            HttpException(
                status_code=400, error_code="update_required", message="Update required"
            ),
            "update_required",
            ConfigEntryState.SETUP_ERROR,
            None,
        ),
        (
            HttpException(
                status_code=500, error_code="unknown", message="Unknown error"
            ),
            None,
            ConfigEntryState.SETUP_RETRY,
            None,
        ),
        (
            InvalidSessionTokenException(
                status_code=403, error_code="invalid_token", message="Invalid token"
            ),
            None,
            ConfigEntryState.SETUP_RETRY,
            "Session token invalid, will renew on next update",
        ),
    ],
)
async def test_update_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
    exception: Exception,
    translation_key: str,
    expected_state: ConfigEntryState,
    expected_log_message: str | None,
) -> None:
    """Test handling of update errors."""
    mock_nintendo_client.update.side_effect = exception

    await setup_integration(hass, mock_config_entry)

    # Ensure no entities are created
    entries = er.async_entries_for_config_entry(
        entity_registry, mock_config_entry.entry_id
    )
    assert len(entries) == 0

    # Ensure the config entry is marked as expected state
    assert mock_config_entry.state is expected_state

    # Ensure the correct translation key is used in the error
    assert mock_config_entry.error_reason_translation_key == translation_key

    # If there's an expected log message, check that it was logged
    if expected_log_message:
        assert expected_log_message in caplog.text


async def test_device_update_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    entity_registry: er.EntityRegistry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test entities of a device the library fails to update become unavailable."""
    await setup_integration(hass, mock_config_entry)
    entity_ids = [
        entry.entity_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
    ]
    assert entity_ids

    async def poll() -> None:
        freezer.tick(60)
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    await poll()
    for entity_id in entity_ids:
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

    # The library logs and swallows errors raised while updating a single
    # device: the update returns, but the device callbacks do not run.
    working_update = mock_nintendo_client.update.side_effect
    mock_nintendo_client.update.side_effect = None
    await poll()

    for entity_id in entity_ids:
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
    assert mock_config_entry.runtime_data.last_update_success
    assert "Updating Nintendo device testdevid failed" in caplog.text

    mock_nintendo_client.update.side_effect = working_update
    await poll()

    for entity_id in entity_ids:
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE
    assert "Nintendo device testdevid is available again" in caplog.text


def _reauth_flows(hass: HomeAssistant, entry: MockConfigEntry) -> list:
    """Return the reauth flows in progress for an entry."""
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(entry.domain)
        if flow["context"]["source"] == SOURCE_REAUTH
        and flow["context"]["entry_id"] == entry.entry_id
    ]


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Trigger the next coordinator update."""
    freezer.tick(60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


REJECTED_TOKEN_ERRORS = [
    pytest.param(
        InvalidSessionTokenException(
            status_code=400, message="Invalid grant", error_code="invalid_grant"
        ),
        id="invalid_grant",
    ),
    pytest.param(
        HttpException(
            status_code=401, message="Unauthorized", error_code="invalid_token"
        ),
        id="http_401",
    ),
]


@pytest.mark.parametrize("exception", REJECTED_TOKEN_ERRORS)
async def test_rejected_token_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_authenticator: MagicMock,
    freezer: FrozenDateTimeFactory,
    exception: Exception,
) -> None:
    """Test a session token revoked after setup starts the reauth flow."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    mock_nintendo_client.update.side_effect = exception
    mock_nintendo_authenticator.async_complete_login.side_effect = (
        InvalidSessionTokenException(
            status_code=400, message="Invalid grant", error_code="invalid_grant"
        )
    )
    await _poll(hass, freezer)

    mock_nintendo_authenticator.async_complete_login.assert_called_with(
        use_session_token=True
    )
    assert len(_reauth_flows(hass, mock_config_entry)) == 1
    assert not mock_config_entry.runtime_data.last_update_success


@pytest.mark.parametrize("exception", REJECTED_TOKEN_ERRORS)
async def test_transient_token_rejection(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_authenticator: MagicMock,
    freezer: FrozenDateTimeFactory,
    exception: Exception,
) -> None:
    """Test a rejection that a fresh login clears does not start reauth."""
    await setup_integration(hass, mock_config_entry)
    logins = mock_nintendo_authenticator.async_complete_login.call_count

    mock_nintendo_client.update.side_effect = exception
    await _poll(hass, freezer)

    assert mock_nintendo_authenticator.async_complete_login.call_count == logins + 1
    assert not _reauth_flows(hass, mock_config_entry)
    coordinator = mock_config_entry.runtime_data
    assert not coordinator.last_update_success

    mock_nintendo_client.update.side_effect = None
    await _poll(hass, freezer)
    assert coordinator.last_update_success


async def test_login_check_unreachable(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_nintendo_client: AsyncMock,
    mock_nintendo_authenticator: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test no reauth is started when the login check cannot reach Nintendo."""
    await setup_integration(hass, mock_config_entry)

    mock_nintendo_client.update.side_effect = HttpException(
        status_code=401, message="Unauthorized", error_code="invalid_token"
    )
    mock_nintendo_authenticator.async_complete_login.side_effect = HttpException(
        status_code=503, message="Service unavailable"
    )
    await _poll(hass, freezer)

    assert not _reauth_flows(hass, mock_config_entry)
    assert not mock_config_entry.runtime_data.last_update_success
