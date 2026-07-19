"""Logging, journal, and audit utilities for SunAllocator."""

import logging
import json

from .settings import ENABLE_JOURNAL

INTEGRATION_LOGGER_NAME = "custom_components.sun_allocator"
_JOURNAL_LOGGER = logging.getLogger(f"{INTEGRATION_LOGGER_NAME}.journal")


def get_logger(name=None):
    """Get a logger for the integration or a submodule."""
    if name is None:
        name = INTEGRATION_LOGGER_NAME
    elif not name.startswith(INTEGRATION_LOGGER_NAME):
        name = f"{INTEGRATION_LOGGER_NAME}.{name}"
    return logging.getLogger(name)


def log_info(msg, *args, **kwargs):
    """Log an info message."""
    get_logger().info(msg, *args, **kwargs)


def log_debug(msg, *args, **kwargs):
    """Log a debug message."""
    get_logger().debug(msg, *args, **kwargs)


def log_warning(msg, *args, **kwargs):
    """Log a warning message."""
    get_logger().warning(msg, *args, **kwargs)


def log_error(msg, *args, **kwargs):
    """Log an error message."""
    get_logger().error(msg, *args, **kwargs)


def journal_event(event_type, data=None):
    """Log a journal event.

    Emitted at DEBUG: the journal is a per-cycle diagnostic trail (e.g. an
    ``excess_power_calc`` line every recalculation), so it must stay silent at normal
    levels — logging it at INFO floods the log with a JSON line every few seconds. It
    reappears when the integration logger is explicitly set to ``debug``.
    """
    if not ENABLE_JOURNAL:
        return
    msg = {
        "event": event_type,
        "data": data or {},
    }
    _JOURNAL_LOGGER.debug("[JOURNAL] %s", json.dumps(msg, ensure_ascii=False))


def audit_action(action, details=None):
    """Log an audit action (DEBUG — see ``journal_event``)."""
    if not ENABLE_JOURNAL:
        return
    msg = {
        "action": action,
        "details": details or {},
    }
    _JOURNAL_LOGGER.debug("[AUDIT] %s", json.dumps(msg, ensure_ascii=False))


def log_exception(context, exc):
    """Log an exception with context."""
    _JOURNAL_LOGGER.error("[EXCEPTION] %s: %s", context, exc, exc_info=True)
