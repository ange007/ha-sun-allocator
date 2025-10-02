"""Utility functions for the Sun Allocator integration."""

import re
from typing import Tuple


def clean_entity_id_and_mode(entity_id_raw: str) -> Tuple[str, str | None]:
    """Normalize entity_id and extract hvac_mode if present."""
    if not entity_id_raw or not isinstance(entity_id_raw, str):
        return entity_id_raw, None
    entity_id = entity_id_raw.strip()
    entity_id = re.sub(r"^[^a-zA-Z0-9]*", "", entity_id)
    # Extract mode if present in parentheses (e.g., (Heat) or (Cool))
    mode_match = re.search(r"\((.*?)\)", entity_id)
    hvac_mode = mode_match.group(1).strip().lower() if mode_match else None
    entity_id = re.sub(r"\s*\(.*?\)", "", entity_id)
    entity_id = re.sub(r"\s*\[.*?\]", "", entity_id)
    entity_id = entity_id.strip()
    return entity_id, hvac_mode
