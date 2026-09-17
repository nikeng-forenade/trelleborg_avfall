"""Rökprovning av integrationens moduler (kräver att homeassistant är installerat).

Körs efter ändringar för att fånga stavfel i importer och API-anrop.
"""

from __future__ import annotations

import pathlib
import sys
import traceback

COMPONENTS = pathlib.Path(__file__).parent.parent / "custom_components"
sys.path.insert(0, str(COMPONENTS))

MODULES = (
    "trelleborg_avfall.const",
    "trelleborg_avfall.api",
    "trelleborg_avfall.coordinator",
    "trelleborg_avfall.config_flow",
    "trelleborg_avfall.sensor",
    "trelleborg_avfall.binary_sensor",
    "trelleborg_avfall.calendar",
    "trelleborg_avfall",
)


def main() -> int:
    try:
        import homeassistant  # noqa: F401
    except ImportError:
        print("homeassistant är inte installerat - hoppar över importtestet.")
        return 0

    failures = 0
    for name in MODULES:
        try:
            __import__(name)
        except Exception:  # noqa: BLE001
            failures += 1
            print(f"FEL  {name}")
            traceback.print_exc(limit=4)
        else:
            print(f"OK   {name}")

    print()
    print(f"{len(MODULES) - failures}/{len(MODULES)} moduler importerade")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
