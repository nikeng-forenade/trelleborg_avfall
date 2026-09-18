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
from homeassistant.util import dt as dt_util

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
    CONF_SCAN_INTERVAL_DAYS,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_STREET_ADDRESS,
    DEFAULT_SCAN_INTERVAL_DAYS,
    DOMAIN,
    HORIZON_REFRESH_DAYS,
)

_LOGGER = logging.getLogger(__name__)


def scan_interval(entry: ConfigEntry) -> timedelta:
    """Uppdateringsintervallet, i dagar.

    Schemat publiceras en säsong i taget, så dagar är rätt enhet. Äldre
    versioner sparade intervallet i minuter och läses fortfarande in.
    """
    days = entry.options.get(CONF_SCAN_INTERVAL_DAYS)
    if days is not None:
        return timedelta(days=days)

    minutes = entry.options.get(CONF_SCAN_INTERVAL_MINUTES)
    if minutes is not None:
        return timedelta(minutes=minutes)

    return timedelta(days=DEFAULT_SCAN_INTERVAL_DAYS)


def _iso(value: dt.datetime | None) -> str | None:
    """Tidpunkt som ISO-text, eller None."""
    return value.isoformat() if value is not None else None


@dataclass(frozen=True)
class ScheduleData:
    """Aktuellt schema för en fastighet."""

    building_id: str
    building_label: str
    pickups: list[Pickup]

    def pickups_on(self, day: dt.date) -> list[Pickup]:
        return [pickup for pickup in self.pickups if pickup.date == day]

    def upcoming(self, from_day: dt.date | None = None) -> list[Pickup]:
        start = from_day or dt_util.now().date()
        return [pickup for pickup in self.pickups if pickup.date >= start]

    def services(self) -> dict[str, Pickup]:
        """Unika kärl, med ett representativt exemplar per kärl."""
        found: dict[str, Pickup] = {}
        for pickup in self.pickups:
            found.setdefault(pickup.service_key, pickup)
        return found

    def next_for(
        self, service_key: str, from_day: dt.date | None = None
    ) -> Pickup | None:
        """Nästa tömning för ett enskilt kärl."""
        start = from_day or dt_util.now().date()
        for pickup in self.pickups:
            if pickup.service_key == service_key and pickup.date >= start:
                return pickup
        return None

    def upcoming_for(self, service_key: str) -> list[Pickup]:
        """Alla kommande tömningar för ett enskilt kärl."""
        return [
            pickup for pickup in self.upcoming() if pickup.service_key == service_key
        ]


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
        self._base_interval = scan_interval(entry)

        # Status för hämtningen. Visas av sensor.*_last_sync och
        # binary_sensor.*_sync_ok så att en trasig hämtning syns i gränssnittet
        # i stället för bara i loggen.
        self.last_attempt: dt.datetime | None = None
        self.last_success: dt.datetime | None = None
        self.last_error: str | None = None
        self.last_error_time: dt.datetime | None = None
        self.consecutive_failures = 0

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._base_interval,
        )

    @property
    def sync_status(self) -> str:
        """'ok' när senaste hämtningen lyckades, annars 'error'."""
        return "ok" if self.last_update_success else "error"

    def status_attributes(self) -> dict[str, object]:
        """Status för hämtningen, till sensor.*_last_sync och *_sync_ok."""
        next_refresh: str | None = None
        if self.last_attempt is not None and self.update_interval is not None:
            next_refresh = (self.last_attempt + self.update_interval).isoformat()

        return {
            "status": self.sync_status,
            "last_attempt": _iso(self.last_attempt),
            "last_success": _iso(self.last_success),
            "last_error": self.last_error,
            "last_error_time": _iso(self.last_error_time),
            "consecutive_failures": self.consecutive_failures,
            "pickups": len(self.data.pickups) if self.data else 0,
            "next_refresh": next_refresh,
        }

    async def _async_update_data(self) -> ScheduleData:
        """Hämta schemat och håll reda på hur det går."""
        self.last_attempt = dt_util.now()
        try:
            data = await self._async_fetch_schedule()
        except Exception as err:  # noqa: BLE001 - allt som går fel ska synas
            self.consecutive_failures += 1
            self.last_error = str(err) or err.__class__.__name__
            self.last_error_time = self.last_attempt
            raise

        self.consecutive_failures = 0
        self.last_error = None
        self.last_success = self.last_attempt
        return data

    async def _async_fetch_schedule(self) -> ScheduleData:
        building = self._building or self._building_from_entry()

        # Schemat ligger på en publik endpoint - kan vi redan fastighets-ID:t
        # behöver vi inte logga in alls.
        if building is not None:
            pickups = await self._async_fetch_public(building.id)
            if pickups:
                self._building = building
                return self._apply_interval(
                    ScheduleData(building.id, building.label, pickups)
                )

        return self._apply_interval(await self._async_update_via_login())

    def _apply_interval(self, data: ScheduleData) -> ScheduleData:
        """Hämta oftare igen när det kända schemat börjar ta slut.

        Portalen publicerar en säsong i taget. Utan det här skulle ett långt
        intervall kunna göra att nästa säsongs datum missas.
        """
        interval = self._base_interval
        if data.pickups:
            horizon = (data.pickups[-1].date - dt_util.now().date()).days
            if horizon <= HORIZON_REFRESH_DAYS:
                interval = min(interval, timedelta(days=1))

        if interval != self.update_interval:
            _LOGGER.debug("Justerar uppdateringsintervallet till %s", interval)
            self.update_interval = interval

        return data

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
                self._client.fetch_schedule, building_id
            )
        except (requests.RequestException, ValueError, TrelleborgError) as err:
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
