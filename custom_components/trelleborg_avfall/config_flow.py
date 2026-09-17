"""Config- och optionsflöde för Trelleborg Avfall."""

from __future__ import annotations

import logging
from typing import Any

import requests
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .api import (
    Building,
    TrelleborgAmbiguousBuildingError,
    TrelleborgAuthError,
    TrelleborgClient,
    TrelleborgError,
    TrelleborgNoBuildingError,
)
from .const import (
    CONF_BUILDING_ID,
    CONF_BUILDING_LABEL,
    CONF_CUSTOMER_ID,
    CONF_IDENTIFICATION_NUMBER,
    CONF_SCAN_INTERVAL_DAYS,
    CONF_STREET_ADDRESS,
    DEFAULT_SCAN_INTERVAL_DAYS,
    DOMAIN,
    MAX_SCAN_INTERVAL_DAYS,
    MIN_SCAN_INTERVAL_DAYS,
)

_LOGGER = logging.getLogger(__name__)


def _labels(buildings: list[Building]) -> str:
    return " | ".join(building.label for building in buildings) or "-"


def _credentials_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_CUSTOMER_ID, default=defaults.get(CONF_CUSTOMER_ID, vol.UNDEFINED)
            ): str,
            vol.Required(
                CONF_IDENTIFICATION_NUMBER,
                default=defaults.get(CONF_IDENTIFICATION_NUMBER, vol.UNDEFINED),
            ): str,
            vol.Optional(
                CONF_STREET_ADDRESS,
                default=defaults.get(CONF_STREET_ADDRESS, vol.UNDEFINED),
            ): str,
        }
    )


class TrelleborgConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Frågar efter kundnummer, personnummer och vid behov adress."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    # -- Ny installation ---------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}

        if user_input is not None:
            entry_data, errors, placeholders = await self._async_validate(user_input)
            if entry_data is not None:
                building_id = entry_data[CONF_BUILDING_ID]
                await self.async_set_unique_id(building_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=entry_data[CONF_BUILDING_LABEL]
                    or f"Trelleborg ({entry_data[CONF_CUSTOMER_ID]})",
                    data=entry_data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(user_input),
            errors=errors,
            description_placeholders=placeholders or None,
        )

    # -- Ny inloggning efter att portalen nekat -----------------------------

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        entry = self._reauth_entry

        if user_input is not None and entry is not None:
            entry_data, errors, placeholders = await self._async_validate(user_input)
            if entry_data is not None:
                return self.async_update_reload_and_abort(entry, data=entry_data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(entry.data if entry else user_input),
            errors=errors,
            description_placeholders=placeholders or None,
        )

    # -- Gemensam validering -----------------------------------------------

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, str], dict[str, str]]:
        """Logga in en gång och verifiera uppgifterna."""
        street_address = (user_input.get(CONF_STREET_ADDRESS) or "").strip() or None
        client = TrelleborgClient(
            user_input[CONF_CUSTOMER_ID], user_input[CONF_IDENTIFICATION_NUMBER]
        )

        try:
            building = await self.hass.async_add_executor_job(
                client.login_and_select_building, street_address
            )
        except TrelleborgAuthError:
            # Portalen låser efter tre felaktiga försök - gör inga omförsök här.
            return None, {"base": "invalid_auth"}, {}
        except TrelleborgNoBuildingError:
            return None, {"base": "no_building"}, {}
        except TrelleborgAmbiguousBuildingError as err:
            return (
                None,
                {"base": "building_not_found"},
                {"buildings": _labels(err.buildings)},
            )
        except (TrelleborgError, requests.RequestException, ValueError) as err:
            _LOGGER.debug("Kunde inte verifiera mot portalen: %s", err)
            return None, {"base": "cannot_connect"}, {}

        return (
            {
                CONF_CUSTOMER_ID: user_input[CONF_CUSTOMER_ID],
                CONF_IDENTIFICATION_NUMBER: user_input[CONF_IDENTIFICATION_NUMBER],
                CONF_STREET_ADDRESS: street_address,
                CONF_BUILDING_ID: building.id,
                CONF_BUILDING_LABEL: building.label,
            },
            {},
            {},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return TrelleborgOptionsFlow()


class TrelleborgOptionsFlow(config_entries.OptionsFlow):
    """Låter användaren styra hur ofta nya tider hämtas."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL_DAYS, DEFAULT_SCAN_INTERVAL_DAYS
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_DAYS, default=current
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL_DAYS,
                            max=MAX_SCAN_INTERVAL_DAYS,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="d",
                        )
                    )
                }
            ),
        )
