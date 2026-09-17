"""Kontrollerar översättningsfilerna.

Körs efter ändringar i texter eller entiteter:
    python dev/check_translations.py

Kontrollerar att filerna är giltig JSON i UTF-8, att strings.json och en.json är
identiska, och att svenska och engelska har exakt samma uppsättning nycklar.
"""

from __future__ import annotations

import json
import pathlib

COMPONENT = (
    pathlib.Path(__file__).parent.parent / "custom_components" / "trelleborg_avfall"
)

FILES = {
    "strings": COMPONENT / "strings.json",
    "en": COMPONENT / "translations" / "en.json",
    "sv": COMPONENT / "translations" / "sv.json",
}


def flatten(payload: object, prefix: str = "") -> dict[str, str]:
    """Gör om nästlade dictar till {'sensor.next_pickup.name': '...'}."""
    flat: dict[str, str] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            flat.update(flatten(value, f"{prefix}{key}."))
    elif isinstance(payload, str):
        flat[prefix.rstrip(".")] = payload
    return flat


def main() -> int:
    data: dict[str, dict[str, str]] = {}
    failed = False

    for name, path in FILES.items():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            print(f"FEL   {name}: {err}")
            failed = True
            continue
        data[name] = flatten(raw)
        print(f"OK    {name} ({len(data[name])} texter)")

    if failed:
        return 1

    if data["strings"] != data["en"]:
        print("FEL   strings.json och en.json är inte identiska")
        only_strings = set(data["strings"]) - set(data["en"])
        only_en = set(data["en"]) - set(data["strings"])
        for key in sorted(only_strings):
            print(f"        bara i strings.json: {key}")
        for key in sorted(only_en):
            print(f"        bara i en.json:      {key}")
        failed = True

    missing_in_sv = set(data["en"]) - set(data["sv"])
    missing_in_en = set(data["sv"]) - set(data["en"])
    for key in sorted(missing_in_sv):
        print(f"FEL   saknas på svenska: {key}")
        failed = True
    for key in sorted(missing_in_en):
        print(f"FEL   saknas på engelska: {key}")
        failed = True

    if not failed:
        print("\nSvenska entitetsnamn:")
        for key, value in sorted(data["sv"].items()):
            if key.startswith("entity."):
                print(f"  {key:42} {value}")

    print()
    print("Allt stämmer." if not failed else "Rätta felen ovan.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
