"""Kalender med alla kommande hämtningar."""

from __future__ import annotations

import datetime as dt

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import Pickup
from .const import DOMAIN
from .coordinator import TrelleborgCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TrelleborgCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TrelleborgCalendar(coordinator, entry)])


def _to_event(pickup: Pickup) -> CalendarEvent:
    start = dt_util.start_of_local_day(pickup.date)
    summary = pickup.waste_type
    if pickup.bin_label:
        summary = f"{summary} · {pickup.bin_label}"

    details = [
        detail for detail in (pickup.bin_description, pickup.frequency) if detail
    ]

    return CalendarEvent(
        start=start,
        end=start + dt.timedelta(days=1),
        summary=summary,
        description=" · ".join(details),
    )


class TrelleborgCalendar(CoordinatorEntity[TrelleborgCoordinator], CalendarEntity):
    """Hämtningsdagar som heldagshändelser."""

    _attr_has_entity_name = True
    _attr_translation_key = "pickups"
    _attr_icon = "mdi:calendar"

    def __init__(self, coordinator: TrelleborgCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_calendar"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Trelleborg Avfall",
            manufacturer="Trelleborgs kommun",
            model=coordinator.data.building_label or entry.title,
        )

    @property
    def event(self) -> CalendarEvent | None:
        upcoming = self.coordinator.data.upcoming()
        return _to_event(upcoming[0]) if upcoming else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: dt.datetime,
        end_date: dt.datetime,
    ) -> list[CalendarEvent]:
        first = dt_util.as_local(start_date).date()
        last = dt_util.as_local(end_date).date()
        return [
            _to_event(pickup)
            for pickup in self.coordinator.data.pickups
            if first <= pickup.date <= last
        ]
