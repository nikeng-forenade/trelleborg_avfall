"""Konstanter för Trelleborg Avfall."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "trelleborg_avfall"

CONF_CUSTOMER_ID: Final = "customer_id"
CONF_IDENTIFICATION_NUMBER: Final = "identification_number"
CONF_STREET_ADDRESS: Final = "street_address"

# Cachas i config entry-data efter första lyckade inloggningen så att portalen
# inte behöver loggas in vid varje uppdatering.
CONF_BUILDING_ID: Final = "building_id"
CONF_BUILDING_LABEL: Final = "building_label"

CONF_SCAN_INTERVAL_DAYS: Final = "scan_interval_days"
# Äldre versioner sparade intervallet i minuter - läses fortfarande in.
CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

DEFAULT_SCAN_INTERVAL_DAYS: Final = 1
MIN_SCAN_INTERVAL_DAYS: Final = 1
MAX_SCAN_INTERVAL_DAYS: Final = 30

# Hämtas oftare när det kända schemat är på väg att ta slut, så att nästa
# säsong inte missas om användaren valt ett långt intervall.
HORIZON_REFRESH_DAYS: Final = 21

PLATFORMS: Final = ["sensor", "binary_sensor", "calendar"]
