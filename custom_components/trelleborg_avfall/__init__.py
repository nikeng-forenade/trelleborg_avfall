"""Setup för Trelleborg Avfall."""

from __future__ import annotations

import datetime as dt
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .api import TrelleborgClient
from .const import (
    CONF_CUSTOMER_ID,
    CONF_IDENTIFICATION_NUMBER,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TrelleborgCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Sätt upp en config entry."""
    client = TrelleborgClient(
        entry.data[CONF_CUSTOMER_ID], entry.data[CONF_IDENTIFICATION_NUMBER]
    )
    coordinator = TrelleborgCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    async def _handle_midnight(now: dt.datetime | None = None) -> None:
        """Se till att 'idag' och 'imorgon' stämmer efter midnatt."""
        coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if isinstance(coordinator, TrelleborgCoordinator):
            coordinator.handle_day_change()

    entry.async_on_unload(
        async_track_time_change(hass, _handle_midnight, hour=0, minute=0, second=5)
    )

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ladda om när användaren ändrar uppdateringsintervallet."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Ta ner en config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded
