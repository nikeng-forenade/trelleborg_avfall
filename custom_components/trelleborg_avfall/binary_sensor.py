"""Binära sensorer för tömning idag och imorgon.

De här är de du bygger automationer på: de slår om strax efter midnatt när det
är dags, så en automation med `to: "on"` körs rätt dag.
"""

from __future__ import annotations

import datetime as dt

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TrelleborgCoordinator

_ENTITIES = (
    ("pickup_today", 0, "mdi:trash-can"),
    ("pickup_tomorrow", 1, "mdi:calendar-arrow-right"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TrelleborgCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            TrelleborgPickupBinarySensor(coordinator, entry, key, offset, icon)
            for key, offset, icon in _ENTITIES
        ]
    )


class TrelleborgPickupBinarySensor(
    CoordinatorEntity[TrelleborgCoordinator], BinarySensorEntity
):
    """På när det finns en hämtning idag (eller imorgon)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrelleborgCoordinator,
        entry: ConfigEntry,
        translation_key: str,
        day_offset: int,
        icon: str,
    ) -> None:
        super().__init__(coordinator)
        self._offset = day_offset
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{translation_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Trelleborg Avfall",
            manufacturer="Trelleborgs kommun",
            model=coordinator.data.building_label or entry.title,
        )

    @property
    def _day(self) -> dt.date:
        return dt.date.today() + dt.timedelta(days=self._offset)

    @property
    def _pickups(self) -> list[str]:
        return [
            pickup.waste_type for pickup in self.coordinator.data.pickups_on(self._day)
        ]

    @property
    def is_on(self) -> bool:
        return bool(self._pickups)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "date": self._day.isoformat(),
            "waste_types": self._pickups,
        }
