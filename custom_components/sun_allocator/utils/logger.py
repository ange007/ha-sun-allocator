import logging

INTEGRATION_LOGGER_NAME = "custom_components.sun_allocator"


def get_logger(name=None):
    """Get a logger for the integration or a submodule."""
    if name is None:
        name = INTEGRATION_LOGGER_NAME
    elif not name.startswith(INTEGRATION_LOGGER_NAME):
        name = f"{INTEGRATION_LOGGER_NAME}.{name}"
    return logging.getLogger(name)


def log_info(msg, *args, **kwargs):
    get_logger().info(msg, *args, **kwargs)

def log_debug(msg, *args, **kwargs):
    get_logger().debug(msg, *args, **kwargs)

def log_warning(msg, *args, **kwargs):
    get_logger().warning(msg, *args, **kwargs)

def log_error(msg, *args, **kwargs):
    get_logger().error(msg, *args, **kwargs)
