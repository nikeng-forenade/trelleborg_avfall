"""Kontrollerar att de Home Assistant-symboler integrationen använder verkligen finns.

Statisk kontroll: Home Assistant kan inte installeras på den här maskinen
(lru-dict kräver en C-kompilator), så i stället läses källkoden i det uppackade
homeassistant-paketet och varje importerad symbol slås upp.

Körs så här:
    python dev/check_ha_symbols.py <sökväg till uppackat homeassistant-paket>
"""

from __future__ import annotations

import ast
import pathlib
import sys

# (modulfil relativt paketroten, symboler integrationen importerar därifrån)
CHECKS: dict[str, tuple[str, ...]] = {
    "config_entries.py": ("ConfigEntry", "ConfigFlow", "OptionsFlow"),
    "core.py": ("HomeAssistant", "callback"),
    "data_entry_flow.py": ("FlowResult",),
    "exceptions.py": ("ConfigEntryAuthFailed",),
    "helpers/selector.py": (
        "NumberSelector",
        "NumberSelectorConfig",
        "NumberSelectorMode",
    ),
    "helpers/update_coordinator.py": (
        "CoordinatorEntity",
        "DataUpdateCoordinator",
        "UpdateFailed",
    ),
    "helpers/device_registry.py": ("DeviceInfo",),
    "helpers/entity_platform.py": ("AddEntitiesCallback",),
    "helpers/event.py": ("async_track_time_change",),
    "util/dt.py": ("as_local", "start_of_local_day"),
    "components/sensor/__init__.py": (
        "SensorDeviceClass",
        "SensorEntity",
        "SensorStateClass",
    ),
    "components/binary_sensor/__init__.py": ("BinarySensorEntity",),
    "components/calendar/__init__.py": ("CalendarEntity", "CalendarEvent"),
}


def top_level_names(tree: ast.Module) -> set[str]:
    """Samla namn som definieras eller importeras på modulnivå."""
    names: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)

    return names


def main() -> int:
    if len(sys.argv) < 2:
        print("Ange sökvägen till det uppackade homeassistant-paketet.")
        return 1

    root = pathlib.Path(sys.argv[1]) / "homeassistant"
    if not root.is_dir():
        print(f"Hittade inte {root}")
        return 1

    versions: dict[str, str] = {}
    const_file = root / "const.py"
    if const_file.is_file():
        for line in const_file.read_text(encoding="utf-8").splitlines():
            for key in ("MAJOR_VERSION", "MINOR_VERSION", "PATCH_VERSION"):
                if line.startswith(f"{key} ="):
                    versions[key] = line.split("=", 1)[1].strip()
    print(
        "Home Assistant "
        + ".".join(
            versions.get(key, "?")
            for key in ("MAJOR_VERSION", "MINOR_VERSION", "PATCH_VERSION")
        )
    )
    print()

    failures = 0
    for relative, symbols in CHECKS.items():
        path = root / relative
        if not path.is_file():
            print(f"SAKNAS  {relative}")
            failures += len(symbols)
            continue

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as err:
            print(f"KAN EJ LÄSAS  {relative}: {err}")
            failures += len(symbols)
            continue

        available = top_level_names(tree)
        missing = [symbol for symbol in symbols if symbol not in available]
        if missing:
            failures += len(missing)
            print(f"SAKNAS  {relative}: {', '.join(missing)}")
        else:
            print(f"OK      {relative}: {', '.join(symbols)}")

    print()
    if failures:
        print(f"{failures} symbol(er) saknas - rätta innan integrationen körs.")
    else:
        print("Alla använda Home Assistant-symboler finns.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
