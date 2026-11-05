"""Packaging checks for the custom integration (not part of core's tests)."""

import json
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from custom_components.nintendo_parental_controls.const import DOMAIN

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / DOMAIN


async def test_overrides_built_in_integration(hass: HomeAssistant) -> None:
    """The custom copy is loaded instead of the built-in integration."""
    integration = await async_get_integration(hass, DOMAIN)
    assert not integration.is_built_in
    assert integration.pkg_path == f"custom_components.{DOMAIN}"
    assert integration.version is not None


def _key_paths(tree: Any, prefix: str = "") -> set[str]:
    if not isinstance(tree, dict):
        return {prefix}
    paths: set[str] = set()
    for key, value in tree.items():
        paths |= _key_paths(value, f"{prefix}/{key}")
    return paths


def test_translations_match_strings() -> None:
    """translations/en.json is the resolved form of strings.json."""
    strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
    english_text = (COMPONENT / "translations" / "en.json").read_text(encoding="utf-8")
    assert "[%key:" not in english_text
    assert _key_paths(json.loads(english_text)) == _key_paths(strings)
