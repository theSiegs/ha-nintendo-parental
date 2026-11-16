"""Fallbacks for Home Assistant releases older than core dev (fork only).

This file is not part of Home Assistant core. Remove it once the oldest
supported Home Assistant release has homeassistant.const.CommonServiceArgument
(2026.12).
"""

from enum import StrEnum


class CommonServiceArgument(StrEnum):
    """Common service argument keys, as in homeassistant.const."""

    DEVICE_ID = "device_id"
    ENTITY_ID = "entity_id"
