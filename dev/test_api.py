"""Utvecklingstest av api.py mot det riktiga kontot.

Körs med uppgifterna i wcs-testets secrets.yaml (gitignorerad) eller via
miljövariablerna TBG_KUNDNUMMER / TBG_PERSONNUMMER.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

SECRETS = pathlib.Path(__file__).parent / "secrets.yaml"

API_PATH = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "trelleborg_avfall"
    / "api.py"
)


# Modulen laddas via filsökväg med ett eget namn. Att lägga integrationsmappen i
# sys.path skulle göra att integrationens calendar.py skuggar standardbibliotekets
# calendar-modul, vilket får requests att krascha.
def _load_api():
    spec = importlib.util.spec_from_file_location("trelleborg_api", API_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Kunde inte läsa {API_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["trelleborg_api"] = module
    spec.loader.exec_module(module)
    return module


api = _load_api()


def credentials() -> tuple[str, str]:
    """Uppgifterna tas från miljövariabler, annars från dev/secrets.yaml."""
    customer_id = os.environ.get("TBG_KUNDNUMMER")
    identity = os.environ.get("TBG_PERSONNUMMER")
    if customer_id and identity:
        return customer_id, identity

    if SECRETS.is_file():
        import yaml

        data = yaml.safe_load(SECRETS.read_text(encoding="utf-8")) or {}
        return (
            str(data.get("customer_id", "")),
            str(data.get("identification_number", "")),
        )

    return "", ""


def main() -> int:
    customer_id, identity = credentials()
    if not customer_id or not identity:
        print(
            "Inga uppgifter hittades. Sätt TBG_KUNDNUMMER och TBG_PERSONNUMMER, "
            "eller skapa dev/secrets.yaml med customer_id och identification_number."
        )
        return 1

    client = api.TrelleborgClient(customer_id, identity)

    print("1. Loggar in och läser fastigheter ...")
    building = client.login_and_select_building()
    print(f"   vald fastighet: id={building.id} label={building.label!r}")

    print("\n2. Nästa tömning per kärl (JSON) ...")
    for pickup in client.get_pickups(building.id):
        print(
            f"   {pickup.date}  {pickup.waste_type:11} "
            f"{pickup.bin_label:24} {pickup.bin_description}"
        )

    print("\n3. Hela schemat (JSON + PDF) ...")
    schedule = client.fetch_schedule(building.id)
    print(f"   {len(schedule)} tömningar totalt")
    for pickup in schedule:
        print(
            f"   {pickup.date}  {pickup.waste_type:11} "
            f"{pickup.bin_label:24} {pickup.bin_description}"
        )

    print("\n4. Kontroll: fungerar det utan session? ...")
    session = client.login()
    json_only = len(client.get_pickups(building.id, session=session))
    full = len(client.fetch_schedule(building.id))
    print(f"   nästa per kärl : {json_only}")
    print(f"   hela schemat   : {full}")

    # OBS: inget test av felaktiga inloggningsuppgifter här.
    # Portalen låser inloggningen efter tre felaktiga försök.

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
