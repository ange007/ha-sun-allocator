"""Sun Allocator config flow - refactored version."""

# Import the refactored config flow classes
from .config import SunAllocatorConfigFlow, async_get_options_flow

# Re-export for Home Assistant
__all__ = ["SunAllocatorConfigFlow", "async_get_options_flow"]
