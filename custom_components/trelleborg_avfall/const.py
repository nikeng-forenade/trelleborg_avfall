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

CONF_SCAN_INTERVAL_MINUTES: Final = "scan_interval_minutes"

DEFAULT_SCAN_INTERVAL_MINUTES: Final = 720  # 12 timmar
MIN_SCAN_INTERVAL_MINUTES: Final = 15
MAX_SCAN_INTERVAL_MINUTES: Final = 10080  # 7 dagar

PLATFORMS: Final = ["sensor", "binary_sensor", "calendar"]
