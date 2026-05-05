"""Internal (non-user-facing) constants shared between core modules.

Kept separate from ``..const`` so that user-facing config keys remain a clean
public surface.
"""

from ..const import (
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
)

# Entity domains that SunAllocator can drive (turn on / off / set power).
SUPPORTED_DOMAINS: frozenset[str] = frozenset({
    DOMAIN_LIGHT,
    DOMAIN_SWITCH,
    DOMAIN_INPUT_BOOLEAN,
    DOMAIN_AUTOMATION,
    DOMAIN_SCRIPT,
    DOMAIN_CLIMATE,
})
