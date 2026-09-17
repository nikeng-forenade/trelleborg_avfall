"""Sensor för nästa hämtning."""

from __future__ import annotations

import datetime as dt

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Pickup
from .const import DOMAIN
from .coordinator import TrelleborgCoordinator

ICON_MAP = {
    "Fyrfack 1": "mdi:recycle",
    "Fyrfack 2": "mdi:recycle",
    "Restavfall": "mdi:trash-can",
    "Matavfall": "mdi:food-apple",
    "Trädgårdsavfall": "mdi:leaf",
}

WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TrelleborgCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TrelleborgNextPickupSensor(coordinator, entry)])


class TrelleborgNextPickupSensor(
    CoordinatorEntity[TrelleborgCoordinator], SensorEntity
):
    """Datum för nästa hämtning, med kommande tömningar som attribut."""

    _attr_has_entity_name = True
    _attr_translation_key = "next_pickup"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self, coordinator: TrelleborgCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_next_pickup"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Trelleborg Avfall",
            manufacturer="Trelleborgs kommun",
            model=coordinator.data.building_label or entry.title,
        )

    @property
    def _next(self) -> Pickup | None:
        upcoming = self.coordinator.data.upcoming()
        return upcoming[0] if upcoming else None

    @property
    def native_value(self) -> dt.date | None:
        pickup = self._next
        return pickup.date if pickup else None

    @property
    def icon(self) -> str:
        pickup = self._next
        if pickup is None:
            return "mdi:calendar-clock"
        return ICON_MAP.get(pickup.waste_type, "mdi:trash-can")

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        upcoming = self.coordinator.data.upcoming()
        pickup = self._next
        if pickup is None:
            return {"upcoming": []}

        today = dt.date.today()
        return {
            "waste_type": pickup.waste_type,
            "bin_size": pickup.bin_size,
            "frequency": pickup.frequency,
            "weekday": WEEKDAYS[pickup.date.weekday()],
            "days_until": (pickup.date - today).days,
            "upcoming": [
                {
                    "date": item.date.isoformat(),
                    "waste_type": item.waste_type,
                    "bin_size": item.bin_size,
                    "days_until": (item.date - today).days,
                }
                for item in upcoming
            ],
        }
