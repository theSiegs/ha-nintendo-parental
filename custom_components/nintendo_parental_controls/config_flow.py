"""Config flow for the Nintendo Switch parental controls integration."""

from collections.abc import Mapping
import logging
from typing import TYPE_CHECKING, Any, override

import probatio
from pynintendoauth.exceptions import HttpException, InvalidSessionTokenException
from pynintendoparental import Authenticator
from pynintendoparental.api import Api

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_TOKEN, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaFlowFormStep,
    SchemaOptionsFlowHandler,
)
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    APP_SETUP_URL,
    CONF_PLAYING_HOLDOVER,
    CONF_SESSION_TOKEN,
    DEFAULT_PLAYING_HOLDOVER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

OPTIONS_SCHEMA = probatio.Schema(
    {
        probatio.Required(
            CONF_PLAYING_HOLDOVER, default=DEFAULT_PLAYING_HOLDOVER
        ): NumberSelector(
            NumberSelectorConfig(
                min=1,
                max=60,
                step=1,
                unit_of_measurement=UnitOfTime.MINUTES,
                mode=NumberSelectorMode.BOX,
            )
        ),
    }
)
OPTIONS_FLOW = {"init": SchemaFlowFormStep(OPTIONS_SCHEMA)}


class NintendoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Nintendo Switch parental controls."""

    def __init__(self) -> None:
        """Initialize a new config flow instance."""
        self.auth: Authenticator | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SchemaOptionsFlowHandler:
        """Get the options flow for this handler."""
        return SchemaOptionsFlowHandler(config_entry, OPTIONS_FLOW)

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors = {}
        if self.auth is None:
            self.auth = Authenticator(client_session=async_get_clientsession(self.hass))

        if user_input is not None:
            nintendo_api = Api(
                self.auth, self.hass.config.time_zone, self.hass.config.language
            )
            try:
                await self.auth.async_complete_login(user_input[CONF_API_TOKEN])
            except ValueError, InvalidSessionTokenException, HttpException:
                errors["base"] = "invalid_auth"
            else:
                if TYPE_CHECKING:
                    assert self.auth.account_id
                await self.async_set_unique_id(self.auth.account_id)
                self._abort_if_unique_id_configured()
            try:
                if "base" not in errors:
                    await nintendo_api.async_get_account_devices()
            except HttpException as err:
                if err.status_code == 404:
                    return self.async_abort(
                        reason="no_devices_found",
                        description_placeholders={"more_info_url": APP_SETUP_URL},
                    )
                errors["base"] = "cannot_connect"
            else:
                if "base" not in errors:
                    return self.async_create_entry(
                        title=self.auth.account_id,
                        data={
                            CONF_SESSION_TOKEN: self.auth.session_token,
                        },
                    )
        return self.async_show_form(
            step_id="user",
            description_placeholders={"link": self.auth.login_url},
            data_schema=probatio.Schema(
                {probatio.Required(probatio.Secret(CONF_API_TOKEN)): str}
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauthentication on an API error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if self.auth is None:
            self.auth = Authenticator(client_session=async_get_clientsession(self.hass))
        if user_input is not None:
            try:
                await self.auth.async_complete_login(user_input[CONF_API_TOKEN])
            except ValueError, InvalidSessionTokenException, HttpException:
                errors["base"] = "invalid_auth"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        **reauth_entry.data,
                        CONF_SESSION_TOKEN: self.auth.session_token,
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"link": self.auth.login_url},
            data_schema=probatio.Schema(
                {probatio.Required(probatio.Secret(CONF_API_TOKEN)): str}
            ),
            errors=errors,
        )
