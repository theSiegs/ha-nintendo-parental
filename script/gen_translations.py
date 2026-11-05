"""Generate translations/en.json from strings.json.

Home Assistant core builds translations at release time and resolves
``[%key:...%]`` references against core's own ``homeassistant/strings.json``.
Custom integrations must ship the resolved file themselves.

Usage:
    python script/gen_translations.py path/to/core/homeassistant/strings.json
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "nintendo_parental_controls"
DOMAIN = COMPONENT.name
REFERENCE = re.compile(r"\[%key:([a-z0-9_:]+)%\]")


def _lookup(tree: dict[str, Any], path: list[str]) -> Any:
    node: Any = tree
    for part in path:
        node = node[part]
    return node


def _resolve(value: Any, sources: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve(item, sources) for key, item in value.items()}
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        parts = match.group(1).split("::")
        if parts[0] == "component":
            if parts[1] != DOMAIN:
                raise ValueError(f"Unsupported reference {match.group(0)}")
            resolved = _lookup(sources["self"], parts[2:])
        else:
            resolved = _lookup(sources["common"], parts)
        return _resolve(resolved, sources)

    return REFERENCE.sub(replace, value)


def main() -> None:
    """Write the resolved English translation file."""
    common = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
    resolved = _resolve(strings, {"common": common, "self": strings})
    target = COMPONENT / "translations" / "en.json"
    target.write_text(
        json.dumps(resolved, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
