# Journal and audit utilities for SunAllocator
import json
from .logger import get_logger

from ..settings import ENABLE_JOURNAL

_JOURNAL_LOGGER = get_logger("journal")


def journal_event(event_type, data=None):
    if not ENABLE_JOURNAL:
        return
    msg = {
        "event": event_type,
        "data": data or {},
    }
    _JOURNAL_LOGGER.info("[JOURNAL] %s", json.dumps(msg, ensure_ascii=False))


def audit_action(action, details=None):
    if not ENABLE_JOURNAL:
        return
    msg = {
        "action": action,
        "details": details or {},
    }
    _JOURNAL_LOGGER.info("[AUDIT] %s", json.dumps(msg, ensure_ascii=False))


def log_exception(context, exc):
    _JOURNAL_LOGGER.error("[EXCEPTION] %s: %s", context, exc, exc_info=True)
