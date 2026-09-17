"""Klient mot Trelleborgs kundportal (EDP FutureWeb) för Kretslopp och vatten.

Portalen har två publika endpoints av intresse:

* ``GetWastePickupSchedule`` - JSON med **nästa** tömning per kärl, inklusive
  kärlets storlek, typ och frekvens.
* ``DownloadWastePickup`` - PDF med **hela** hämtschemat per kärl.

Adressökningen i portalen returnerar inga träffar, så en inloggning behövs för
att koppla ett kundnummer till rätt fastighets-ID. När ID:t är känt kan allt
hämtas utan session.

PDF:en innehåller även namn och adress. Den här modulen läser bara ut tjänste-ID,
kärlnamn och datum ur den - inget annat sparas.

Modulen är medvetet fri från Home Assistant-beroenden så att den går att testa
fristående.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

try:  # pypdf används bara för att läsa hämtschemat
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - paketet deklareras i manifest.json
    PdfReader = None  # type: ignore[assignment]

BASE_URL = "https://kretsloppochvatten.trelleborg.se/EDPFutureWeb"
LOGIN_PAGE_URL = f"{BASE_URL}/EDPLogin/Login"
LOGIN_URL = f"{BASE_URL}/EDPLogin/Authenticate"
SELECT_BUILDING_URL = f"{BASE_URL}/MyServices/SelectBuilding"
SCHEDULE_URL = f"{BASE_URL}/SimpleWastePickup/GetWastePickupSchedule"
DOWNLOAD_URL = f"{BASE_URL}/SimpleWastePickup/DownloadWastePickup"

REQUEST_TIMEOUT = 30

_LOGGER = logging.getLogger(__name__)

# "tis 29 sep 2026" -> datum. Veckodagen varierar, månaden är på svenska.
_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)\s+(\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "maj": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "nov": 11,
    "dec": 12,
}
_SERVICE_ID_PATTERN = re.compile(r"Tj[äa]nst:\s*(\d+)")

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
    """En inplanerad hämtning av en specifik tunna."""

    date: dt.date
    waste_type: str
    bin_size: str | None = None
    container_type: str | None = None
    bin_code: str | None = None
    bin_description: str | None = None
    frequency: str | None = None
    service_id: str | None = None

    @property
    def bin_label(self) -> str:
        """Kort beskrivning av tunnan, t.ex. '370 l Fyrfackskärl'."""
        return " ".join(part for part in (self.bin_size, self.container_type) if part)


@dataclass(frozen=True)
class ServiceCalendar:
    """En tjänst (ett kärl) med alla sina datum i hämtschemat."""

    service_id: str
    waste_type: str
    dates: list[dt.date]


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


def parse_hamtschema(text: str) -> list[ServiceCalendar]:
    """Plocka ut tjänste-ID, kärlnamn och datum ur hämtschemats textsidor.

    PDF:en har en tjänst per sida: kärlnamnet står direkt före 'Tjänst: <id>'
    och därefter följer alla datum. Övrig text (namn, adress) ignoreras.
    """
    calendars: list[ServiceCalendar] = []

    for page in text.split("\f"):
        lines = [line.strip() for line in page.splitlines()]
        for index, line in enumerate(lines):
            match = _SERVICE_ID_PATTERN.search(line)
            if not match:
                continue

            waste_type = ""
            for previous in reversed(lines[:index]):
                if previous and not _SERVICE_ID_PATTERN.search(previous):
                    waste_type = previous
                    break

            dates = sorted(
                {
                    dt.date(int(year), _MONTHS[month.lower()], int(day))
                    for day, month, year in _DATE_PATTERN.findall(page)
                }
            )

            if dates:
                calendars.append(
                    ServiceCalendar(
                        service_id=match.group(1),
                        waste_type=waste_type,
                        dates=dates,
                    )
                )
            break

    return calendars


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
                f"Adressen '{street_address}' matchade flera av kontots fastigheter.",
                matches,
            )

        if len(buildings) == 1:
            return buildings[0]

        raise TrelleborgAmbiguousBuildingError(
            "Kontot har flera fastigheter, ange vilken som avses.",
            buildings,
        )

    def login_and_select_building(self, street_address: str | None = None) -> Building:
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
                    container_type=bin_type.get("ContainerType"),
                    bin_code=bin_type.get("Code"),
                    bin_description=service.get("Description"),
                    frequency=service.get("WastePickupFrequency"),
                    service_id=str(service.get("ID") or "") or None,
                )
            )

        pickups.sort(key=lambda pickup: (pickup.date, pickup.waste_type))
        return pickups

    # -- Hela schemat (PDF) -------------------------------------------------

    def get_service_calendar(
        self, building_id: str, session: requests.Session | None = None
    ) -> list[ServiceCalendar]:
        """Hämta hämtschemat som PDF och plocka ut alla datum per kärl."""
        if PdfReader is None:
            raise TrelleborgError(
                "pypdf saknas, kan inte läsa hämtschemat. Installera om integrationen."
            )

        response = (session or requests).post(
            DOWNLOAD_URL,
            data={"searchAdress": f"({building_id})"},
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()

        if "pdf" not in (response.headers.get("Content-Type") or "").lower():
            raise TrelleborgError("Portalen returnerade ingen PDF med hämtschemat.")

        reader = PdfReader(io.BytesIO(response.content))
        text = "\f".join(page.extract_text() or "" for page in reader.pages)
        return parse_hamtschema(text)

    # -- Sammanslaget schema ------------------------------------------------

    def fetch_schedule(self, building_id: str) -> list[Pickup]:
        """Returnera alla kända tömningar för fastigheten.

        PDF:en ger hela schemat medan JSON-svaret ger kärlets egenskaper.
        Kopplingen görs på tjänste-ID. Går PDF:en inte att läsa faller vi
        tillbaka på nästa tömning per kärl.
        """
        services = self.get_pickups(building_id)

        try:
            calendar = self.get_service_calendar(building_id)
        except (TrelleborgError, requests.RequestException, ValueError) as err:
            _LOGGER.debug(
                "Kunde inte läsa hämtschemat, använder nästa tömning: %s", err
            )
            return services

        if not calendar:
            return services

        by_service = {entry.service_id: entry for entry in calendar}
        pickups: list[Pickup] = []
        matched: set[str] = set()

        for service in services:
            entry = by_service.get(service.service_id or "")
            if entry is None:
                # Ingen PDF-post för tjänsten - behåll nästa tömning.
                pickups.append(service)
                continue

            matched.add(entry.service_id)
            pickups.extend(
                Pickup(
                    date=day,
                    waste_type=service.waste_type,
                    bin_size=service.bin_size,
                    container_type=service.container_type,
                    bin_code=service.bin_code,
                    bin_description=service.bin_description,
                    frequency=service.frequency,
                    service_id=service.service_id,
                )
                for day in entry.dates
            )

        # Kärl som bara finns i hämtschemat men inte i JSON-svaret.
        for entry in calendar:
            if entry.service_id in matched:
                continue
            pickups.extend(
                Pickup(
                    date=day,
                    waste_type=entry.waste_type,
                    service_id=entry.service_id,
                )
                for day in entry.dates
            )

        pickups.sort(key=lambda pickup: (pickup.date, pickup.waste_type))
        return pickups
