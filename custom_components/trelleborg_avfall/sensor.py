"""Sensor för nästa hämtning."""

from __future__ import annotations

import datetime as dt

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import Pickup
from .const import DOMAIN
from .coordinator import ScheduleData, TrelleborgCoordinator

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


def _device_info(coordinator: TrelleborgCoordinator, entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Trelleborg Avfall",
        manufacturer="Trelleborgs kommun",
        model=coordinator.data.building_label or entry.title,
    )


def _bin_name(schedule: ScheduleData, service_key: str) -> str:
    """Kärlets namn, t.ex. 'Fyrfack 1'. Vid namnkolision läggs storleken till."""
    services = schedule.services()
    representative = services.get(service_key)
    if representative is None:
        return service_key

    name = representative.waste_type
    duplicates = [
        key
        for key, pickup in services.items()
        if pickup.waste_type == name and key != service_key
    ]
    if duplicates and representative.bin_size:
        return f"{name} ({representative.bin_size})"
    return name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TrelleborgCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            TrelleborgNextPickupSensor(coordinator, entry),
            TrelleborgDaysUntilSensor(coordinator, entry),
            TrelleborgNextWasteTypeSensor(coordinator, entry),
            TrelleborgLastSyncSensor(coordinator, entry),
        ]
    )

    # Ett kärl per tjänst. Nya kärl som dyker upp senare läggs till löpande.
    known: set[str] = set()

    @callback
    def _async_add_new_services() -> None:
        new_entities: list[SensorEntity] = []
        for service_key in coordinator.data.services():
            if service_key in known:
                continue
            known.add(service_key)
            bin_name = _bin_name(coordinator.data, service_key)
            new_entities.append(
                TrelleborgServiceSensor(coordinator, entry, service_key, bin_name)
            )
            new_entities.append(
                TrelleborgServiceDaysUntilSensor(
                    coordinator, entry, service_key, bin_name
                )
            )
        if new_entities:
            async_add_entities(new_entities)

    _async_add_new_services()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_services))


class TrelleborgSensorBase(CoordinatorEntity[TrelleborgCoordinator], SensorEntity):
    """Gemensam bas med enhetsinfo och hjälpare."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TrelleborgCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def _today(self) -> dt.date:
        return dt_util.now().date()

    @property
    def _next(self) -> Pickup | None:
        upcoming = self.coordinator.data.upcoming()
        return upcoming[0] if upcoming else None


class TrelleborgNextPickupSensor(TrelleborgSensorBase):
    """Datum för nästa hämtning, med kommande tömningar som attribut."""

    _attr_translation_key = "next_pickup"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: TrelleborgCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_pickup")

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

        today = self._today
        return {
            "waste_type": pickup.waste_type,
            "bin": pickup.bin_label,
            "bin_size": pickup.bin_size,
            "container_type": pickup.container_type,
            "bin_code": pickup.bin_code,
            "bin_description": pickup.bin_description,
            "frequency": pickup.frequency,
            "weekday": WEEKDAYS[pickup.date.weekday()],
            "days_until": (pickup.date - today).days,
            "upcoming": [
                {
                    "date": item.date.isoformat(),
                    "waste_type": item.waste_type,
                    "bin": item.bin_label,
                    "bin_description": item.bin_description,
                    "days_until": (item.date - today).days,
                }
                for item in upcoming
            ],
        }


class TrelleborgDaysUntilSensor(TrelleborgSensorBase):
    """Antal dagar till nästa tömning."""

    _attr_translation_key = "days_until_pickup"
    _attr_icon = "mdi:calendar-today"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: TrelleborgCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "days_until_pickup")

    @property
    def native_value(self) -> int | None:
        pickup = self._next
        return (pickup.date - self._today).days if pickup else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        pickup = self._next
        if pickup is None:
            return {}
        return {
            "date": pickup.date.isoformat(),
            "waste_type": pickup.waste_type,
            "bin": pickup.bin_label,
            "bin_description": pickup.bin_description,
        }


class TrelleborgNextWasteTypeSensor(TrelleborgSensorBase):
    """Vilken tunna som är näst på tur."""

    _attr_translation_key = "next_waste_type"
    _attr_icon = "mdi:trash-can"

    def __init__(self, coordinator: TrelleborgCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_waste_type")

    @property
    def native_value(self) -> str | None:
        pickup = self._next
        return pickup.waste_type if pickup else None

    @property
    def icon(self) -> str:
        pickup = self._next
        if pickup is None:
            return "mdi:trash-can"
        return ICON_MAP.get(pickup.waste_type, "mdi:trash-can")

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        pickup = self._next
        if pickup is None:
            return {}
        return {
            "date": pickup.date.isoformat(),
            "bin": pickup.bin_label,
            "bin_description": pickup.bin_description,
            "days_until": (pickup.date - self._today).days,
        }


class TrelleborgServiceSensor(TrelleborgSensorBase):
    """Nästa tömning för ett enskilt kärl."""

    _attr_translation_key = "service_next_pickup"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:trash-can"

    def __init__(
        self,
        coordinator: TrelleborgCoordinator,
        entry: ConfigEntry,
        service_key: str,
        bin_name: str,
    ) -> None:
        super().__init__(coordinator, entry, f"service_{service_key}")
        self._service_key = service_key
        self._attr_translation_placeholders = {"bin": bin_name}

    def _representative(self) -> Pickup | None:
        return self.coordinator.data.services().get(self._service_key)

    @property
    def native_value(self) -> dt.date | None:
        pickup = self.coordinator.data.next_for(self._service_key)
        return pickup.date if pickup else None

    @property
    def icon(self) -> str:
        representative = self._representative()
        if representative is None:
            return "mdi:trash-can"
        return ICON_MAP.get(representative.waste_type, "mdi:trash-can")

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        upcoming = self.coordinator.data.upcoming_for(self._service_key)
        if not upcoming:
            return {}

        pickup = upcoming[0]
        return {
            "waste_type": pickup.waste_type,
            "bin": pickup.bin_label,
            "bin_description": pickup.bin_description,
            "frequency": pickup.frequency,
            "days_until": (pickup.date - self._today).days,
            "upcoming": [item.date.isoformat() for item in upcoming],
        }


class TrelleborgServiceDaysUntilSensor(TrelleborgSensorBase):
    """Antal dagar kvar till ett enskilt kärls nästa tömning."""

    _attr_translation_key = "service_days_until"
    _attr_icon = "mdi:calendar-today"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: TrelleborgCoordinator,
        entry: ConfigEntry,
        service_key: str,
        bin_name: str,
    ) -> None:
        super().__init__(coordinator, entry, f"service_{service_key}_days_until")
        self._service_key = service_key
        self._attr_translation_placeholders = {"bin": bin_name}

    @property
    def native_value(self) -> int | None:
        pickup = self.coordinator.data.next_for(self._service_key)
        return (pickup.date - self._today).days if pickup else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        pickup = self.coordinator.data.next_for(self._service_key)
        if pickup is None:
            return {}
        return {
            "date": pickup.date.isoformat(),
            "waste_type": pickup.waste_type,
            "bin": pickup.bin_label,
            "bin_description": pickup.bin_description,
        }


class TrelleborgLastSyncSensor(TrelleborgSensorBase):
    """När schemat senast hämtades från portalen utan problem.

    Alltid tillgänglig: den ska kunna visa att hämtningen misslyckats i stället
    för att försvinna, och attributen säger vad som gick fel.
    """

    _attr_translation_key = "last_sync"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: TrelleborgCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "last_sync")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> dt.datetime | None:
        return self.coordinator.last_success

    @property
    def icon(self) -> str:
        if self.coordinator.sync_status == "ok":
            return "mdi:cloud-check"
        return "mdi:cloud-off-outline"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return self.coordinator.status_attributes()
