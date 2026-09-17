"""Hämtar och cachar hämtningsdagar från Trelleborgs kundportal."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from datetime import timedelta

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    Building,
    Pickup,
    TrelleborgAmbiguousBuildingError,
    TrelleborgAuthError,
    TrelleborgClient,
    TrelleborgError,
    TrelleborgNoBuildingError,
)
from .const import (
    CONF_BUILDING_ID,
    CONF_BUILDING_LABEL,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_STREET_ADDRESS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduleData:
    """Aktuellt schema för en fastighet."""

    building_id: str
    building_label: str
    pickups: list[Pickup]

    def pickups_on(self, day: dt.date) -> list[Pickup]:
        return [pickup for pickup in self.pickups if pickup.date == day]

    def upcoming(self, from_day: dt.date | None = None) -> list[Pickup]:
        start = from_day or dt.date.today()
        return [pickup for pickup in self.pickups if pickup.date >= start]


class TrelleborgCoordinator(DataUpdateCoordinator[ScheduleData]):
    """Uppdaterar schemat med ett intervall som användaren kan ställa in."""

    def __init__(
        self, hass: HomeAssistant, client: TrelleborgClient, entry: ConfigEntry
    ) -> None:
        self._client = client
        self._entry = entry
        # Fastighets-ID:t cachas i minnet. Config entry-data rörs inte här, för
        # en sådan ändring skulle kunna trigga en omladdning av posten.
        self._building: Building | None = None

        minutes = entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )

    async def _async_update_data(self) -> ScheduleData:
        building = self._building or self._building_from_entry()

        # Schemat ligger på en publik endpoint - kan vi redan fastighets-ID:t
        # behöver vi inte logga in alls.
        if building is not None:
            pickups = await self._async_fetch_public(building.id)
            if pickups:
                self._building = building
                return ScheduleData(building.id, building.label, pickups)

        return await self._async_update_via_login()

    def _building_from_entry(self) -> Building | None:
        building_id = self._entry.data.get(CONF_BUILDING_ID)
        if not building_id:
            return None
        return Building(
            id=building_id, label=self._entry.data.get(CONF_BUILDING_LABEL, "")
        )

    async def _async_fetch_public(self, building_id: str) -> list[Pickup]:
        try:
            return await self.hass.async_add_executor_job(
                self._client.get_pickups, building_id
            )
        except (requests.RequestException, ValueError) as err:
            _LOGGER.debug(
                "Kunde inte läsa schemat utan inloggning (%s), loggar in", err
            )
            return []

    async def _async_update_via_login(self) -> ScheduleData:
        street_address = self._entry.data.get(CONF_STREET_ADDRESS) or None
        try:
            building = await self.hass.async_add_executor_job(
                self._client.login_and_select_building, street_address
            )
        except TrelleborgAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (TrelleborgNoBuildingError, TrelleborgAmbiguousBuildingError) as err:
            raise UpdateFailed(str(err)) from err
        except TrelleborgError as err:
            raise UpdateFailed(str(err)) from err
        except requests.RequestException as err:
            raise UpdateFailed(f"Kunde inte nå portalen: {err}") from err
        except ValueError as err:
            raise UpdateFailed(f"Oväntat svar från portalen: {err}") from err

        pickups = await self._async_fetch_public(building.id)
        if not pickups:
            raise UpdateFailed(
                "Portalen returnerade inga hämtningsdagar för fastigheten."
            )

        self._building = building
        return ScheduleData(building.id, building.label, pickups)

    def handle_day_change(self) -> None:
        """Räkna om 'idag/imorgon' vid midnatt utan att hämta nya data."""
        self.async_set_updated_data(self.data)
