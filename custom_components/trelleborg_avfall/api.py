"""Klient mot Trelleborgs kundportal (EDP FutureWeb) för Kretslopp och vatten.

Portalen publicerar hämtningsdagarna på en publik endpoint, men adressökningen
där returnerar inga träffar. En inloggning behövs därför bara för att koppla ett
kundnummer till rätt fastighets-ID. När ID:t är känt kan schemat hämtas utan
session.

Den här modulen är medvetet fri från Home Assistant-beroenden så att den går att
testa fristående.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://kretsloppochvatten.trelleborg.se/EDPFutureWeb"
LOGIN_PAGE_URL = f"{BASE_URL}/EDPLogin/Login"
LOGIN_URL = f"{BASE_URL}/EDPLogin/Authenticate"
SELECT_BUILDING_URL = f"{BASE_URL}/MyServices/SelectBuilding"
SCHEDULE_URL = f"{BASE_URL}/SimpleWastePickup/GetWastePickupSchedule"

REQUEST_TIMEOUT = 30

# Portalen svarar med den här texten när kombinationen inte finns.
_LOGIN_FAILED_MARKERS = ("saknas i v", "LoginErrorMessage")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class TrelleborgError(Exception):
    """Basklass för fel från Trelleborgs portalklient."""


class TrelleborgAuthError(TrelleborgError):
    """Kundnummer och personnummer matchade ingen kund."""


class TrelleborgNoBuildingError(TrelleborgError):
    """Kontot har ingen fastighet med avfallshämtning."""


class TrelleborgAmbiguousBuildingError(TrelleborgError):
    """Kontot har flera fastigheter och ingen entydig träff hittades."""

    def __init__(self, message: str, buildings: list[Building]) -> None:
        super().__init__(message)
        self.buildings = buildings


@dataclass(frozen=True)
class Building:
    """En fastighet kopplad till kontot."""

    id: str
    label: str


@dataclass(frozen=True)
class Pickup:
    """En inplanerad hämtning."""

    date: dt.date
    waste_type: str
    bin_size: str | None = None
    frequency: str | None = None


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _format_bin_size(bin_type: dict) -> str | None:
    size = bin_type.get("Size")
    unit = bin_type.get("Unit")
    if size is None:
        return None
    try:
        number = float(size)
    except (TypeError, ValueError):
        return None
    amount = int(number) if number.is_integer() else number
    return f"{amount} {unit}".strip() if unit else str(amount)


class TrelleborgClient:
    """Hämtar hämtningsdagar från Trelleborgs kundportal."""

    def __init__(self, customer_id: str, identification_number: str) -> None:
        self._customer_id = _digits(customer_id)
        self._identification_number = _digits(identification_number)

    # -- Inloggning --------------------------------------------------------

    def login(self) -> requests.Session:
        """Logga in och returnera en autentiserad session.

        Portalen låser inloggningen efter tre felaktiga försök, så den här
        metoden anropas bara när fastighets-ID:t inte redan är känt.
        """
        session = requests.Session()
        session.headers.update(
            {"User-Agent": _USER_AGENT, "Accept-Language": "sv-SE,sv;q=0.9"}
        )

        session.get(LOGIN_PAGE_URL, timeout=REQUEST_TIMEOUT).raise_for_status()
        response = session.post(
            LOGIN_URL,
            data={
                "CustomerId": self._customer_id,
                "Identitynumber": self._identification_number,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        if any(marker in response.text for marker in _LOGIN_FAILED_MARKERS):
            raise TrelleborgAuthError(
                "Kombinationen av kundnummer och personnummer/organisationsnummer "
                "finns inte i portalen."
            )

        return session

    # -- Fastigheter -------------------------------------------------------

    def get_buildings(self, session: requests.Session) -> list[Building]:
        """Läs ut kontots fastigheter från väljarlistan i portalen."""
        response = session.get(SELECT_BUILDING_URL, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        select = soup.find("select", {"name": "SelectedBuildingID"})
        if select is None:
            select = soup.find("select")

        buildings: list[Building] = []
        if select is not None:
            for option in select.find_all("option"):
                value = (option.get("value") or "").strip()
                if value:
                    label = " ".join(option.get_text(" ", strip=True).split())
                    buildings.append(Building(id=value, label=label))

        if not buildings:
            raise TrelleborgNoBuildingError(
                "Portalen listade ingen fastighet med avfallshämtning för kontot."
            )

        return buildings

    @staticmethod
    def resolve_building(
        buildings: list[Building], street_address: str | None = None
    ) -> Building:
        """Välj fastighet, eventuellt med hjälp av en del av adressen."""
        if street_address:
            wanted = street_address.casefold().strip()
            matches = [b for b in buildings if wanted in b.label.casefold()]
            if len(matches) == 1:
                return matches[0]
            if not matches:
                raise TrelleborgAmbiguousBuildingError(
                    f"Adressen '{street_address}' matchade ingen av kontots "
                    "fastigheter.",
                    buildings,
                )
            raise TrelleborgAmbiguousBuildingError(
                f"Adressen '{street_address}' matchade flera av kontots "
                "fastigheter.",
                matches,
            )

        if len(buildings) == 1:
            return buildings[0]

        raise TrelleborgAmbiguousBuildingError(
            "Kontot har flera fastigheter, ange vilken som avses.",
            buildings,
        )

    def login_and_select_building(
        self, street_address: str | None = None
    ) -> Building:
        session = self.login()
        return self.resolve_building(self.get_buildings(session), street_address)

    # -- Hämtningsdagar ----------------------------------------------------

    def get_pickups(
        self, building_id: str, session: requests.Session | None = None
    ) -> list[Pickup]:
        """Hämta hämtningsdagar för en fastighet.

        Endpointen är publik och kräver ingen session, men parenteserna runt
        ID:t måste vara med - utan dem svarar portalen med HTTP 500.
        """
        requester = session or requests
        if session is not None:
            session.headers.update({"User-Agent": _USER_AGENT})

        response = requester.get(
            SCHEDULE_URL,
            params={"address": f"({building_id})"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        pickups: list[Pickup] = []
        for service in response.json().get("RhServices") or []:
            waste_type = service.get("WasteType")
            next_pickup = service.get("NextWastePickup")
            if not waste_type or not next_pickup:
                continue

            bin_type = service.get("BinType") or {}
            pickups.append(
                Pickup(
                    date=dt.datetime.fromisoformat(next_pickup).date(),
                    waste_type=waste_type,
                    bin_size=_format_bin_size(bin_type),
                    frequency=service.get("WastePickupFrequency"),
                )
            )

        pickups.sort(key=lambda pickup: (pickup.date, pickup.waste_type))
        return pickups
