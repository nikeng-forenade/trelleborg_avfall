"""Kontrollerar blueprint-filerna i blueprints/automation/trelleborg_avfall.

Kontrollen är statisk: Home Assistant går inte att köra här, så i stället
läses YAML:en med en loader som accepterar `!input`-taggen och därefter
verifieras stommen (namn, domän, utlösare, åtgärder) samt att varje `!input`
faktiskt finns definierat under blueprint.input.

Körs så här:
    python dev/check_blueprints.py
"""

from __future__ import annotations

import pathlib
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover - hjälpmeddelande
    sys.exit("PyYAML saknas. Installera med: python -m pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parent.parent
BLUEPRINT_FOLDER = ROOT / "blueprints" / "automation" / "trelleborg_avfall"
INPUT_REF = re.compile(r"!input\s+([A-Za-z0-9_]+)")


class BlueprintLoader(yaml.SafeLoader):
    """SafeLoader som accepterar Home Assistants taggar, t.ex. `!input`."""


def _construct_unknown(loader: BlueprintLoader, tag_suffix: str, node: yaml.Node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


BlueprintLoader.add_multi_constructor("!", _construct_unknown)


def check_file(path: pathlib.Path) -> list[str]:
    """Returnera en lista med problem för en blueprint-fil."""
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    try:
        data = yaml.load(text, Loader=BlueprintLoader)
    except yaml.YAMLError as err:
        return [f"ogiltig YAML: {err}"]

    if not isinstance(data, dict):
        return ["filen innehåller inte ett YAML-objekt"]

    meta = data.get("blueprint")
    if not isinstance(meta, dict):
        return ["blueprint-nyckeln saknas"]

    inputs = meta.get("input") or {}
    if not meta.get("name"):
        problems.append("blueprint.name saknas")
    if meta.get("domain") != "automation":
        problems.append("blueprint.domain måste vara 'automation'")
    if not meta.get("description"):
        problems.append("blueprint.description saknas")
    if not inputs:
        problems.append("blueprint.input saknas")

    if "triggers" not in data and "trigger" not in data:
        problems.append("triggers saknas")
    if "actions" not in data and "action" not in data:
        problems.append("actions saknas")

    referenced = set(INPUT_REF.findall(text))
    for name in sorted(referenced - set(inputs)):
        problems.append(f"!input {name} är inte definierat under blueprint.input")

    unused = sorted(set(inputs) - referenced)
    if unused:
        problems.append(f"input som aldrig används: {', '.join(unused)}")

    for name, spec in inputs.items():
        if isinstance(spec, dict) and not spec.get("selector"):
            problems.append(f"input '{name}' saknar selector")

    return problems


def main() -> int:
    files = sorted(BLUEPRINT_FOLDER.glob("*.yaml"))
    if not files:
        print(f"Hittade inga blueprints i {BLUEPRINT_FOLDER}")
        return 1

    failed = 0
    for path in files:
        problems = check_file(path)
        if problems:
            failed += 1
            print(f"FEL  {path.relative_to(ROOT)}")
            for problem in problems:
                print(f"       - {problem}")
        else:
            print(f"OK   {path.relative_to(ROOT)}")

    print(f"\n{len(files) - failed}/{len(files)} blueprints OK")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
