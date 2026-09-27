"""UI setup, property selection, reauthentication, and polling options."""

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    CannotConnect,
    CondoControlClient,
    CondoControlError,
    InvalidAuth,
    PackagesNotEnabled,
    TwoFactorRequired,
    Workspace,
)
from .const import (
    CONF_POLL_INTERVAL,
    CONF_PROPERTY_TIME_ZONE,
    CONF_USER_ID,
    CONF_WORKSPACE_ID,
    CONF_WORKSPACE_NAME,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)

CREDENTIALS = vol.Schema(
    {
        vol.Required(CONF_EMAIL): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.EMAIL, autocomplete="email"
            )
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD, autocomplete="current-password"
            )
        ),
    }
)


def error_key(error: CondoControlError) -> str:
    if isinstance(error, TwoFactorRequired):
        return "two_factor_required"
    if isinstance(error, InvalidAuth):
        return "invalid_auth"
    if isinstance(error, CannotConnect):
        return "cannot_connect"
    if isinstance(error, PackagesNotEnabled):
        return "packages_not_enabled"
    return "invalid_response"


def options_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_POLL_INTERVAL,
                default=defaults.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
            ),
            vol.Required(
                CONF_PROPERTY_TIME_ZONE, default=defaults[CONF_PROPERTY_TIME_ZONE]
            ): cv.time_zone,
        }
    )


class CondoControlConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, str] = {}
        self._workspaces: list[Workspace] = []
        self._client: CondoControlClient | None = None

    def _new_client(self, user_input: Mapping[str, Any]) -> CondoControlClient:
        self._credentials = {
            CONF_EMAIL: user_input[CONF_EMAIL].strip().lower(),
            CONF_PASSWORD: user_input[CONF_PASSWORD],
        }
        return CondoControlClient(
            async_get_clientsession(self.hass),
            self._credentials[CONF_EMAIL],
            self._credentials[CONF_PASSWORD],
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            self._client = self._new_client(user_input)
            try:
                await self._client.login()
                self._workspaces = await self._client.list_workspaces()
            except CondoControlError as err:
                errors["base"] = error_key(err)
            else:
                if not self._workspaces:
                    return self.async_abort(reason="no_workspaces")
                # Always show this step, even for exactly one property.
                return await self.async_step_property()
        return self.async_show_form(
            step_id="user", data_schema=CREDENTIALS, errors=errors
        )

    async def async_step_property(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            selected = next(
                (
                    item
                    for item in self._workspaces
                    if str(item.id) == user_input[CONF_WORKSPACE_ID]
                ),
                None,
            )
            if selected is None:
                errors["base"] = "invalid_property"
            else:
                assert self._client is not None
                try:
                    selected = await self._client.select_workspace(selected.id)
                    await self._client.get_packages()
                except CondoControlError as err:
                    errors["base"] = error_key(err)
                else:
                    await self.async_set_unique_id(f"{selected.id}_{selected.user_id}")
                    self._abort_if_unique_id_configured()
                    resident = (
                        user_input.get(CONF_NAME, "").strip()
                        or selected.resident_name
                        or self._credentials[CONF_EMAIL]
                    )
                    return self.async_create_entry(
                        title=f"{resident} — {selected.name}",
                        data={
                            **self._credentials,
                            CONF_NAME: resident,
                            CONF_WORKSPACE_ID: selected.id,
                            CONF_WORKSPACE_NAME: selected.name,
                            CONF_USER_ID: selected.user_id,
                        },
                        options={
                            CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                            CONF_PROPERTY_TIME_ZONE: user_input[
                                CONF_PROPERTY_TIME_ZONE
                            ],
                        },
                    )
        choices = [
            selector.SelectOptionDict(value=str(item.id), label=item.name)
            for item in self._workspaces
        ]
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WORKSPACE_ID, default=choices[0]["value"]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=choices, mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(CONF_NAME): selector.TextSelector(),
            }
        ).extend(
            options_schema({CONF_PROPERTY_TIME_ZONE: self.hass.config.time_zone}).schema
        )
        return self.async_show_form(
            step_id="property", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            client = self._new_client(user_input)
            try:
                await client.login()
                workspace = await client.select_workspace(entry.data[CONF_WORKSPACE_ID])
                await self.async_set_unique_id(f"{workspace.id}_{workspace.user_id}")
                self._abort_if_unique_id_mismatch()
                await client.get_packages()
            except CondoControlError as err:
                errors["base"] = error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=self._credentials
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS, {CONF_EMAIL: entry.data[CONF_EMAIL]}
            ),
            description_placeholders={"name": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        return CondoControlOptionsFlow()


class CondoControlOptionsFlow(OptionsFlowWithReload):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=options_schema(self.config_entry.options)
        )
