import sys
import unittest.mock
import pytest

# Mock the 'resource' module on Windows
if sys.platform == "win32":
    sys.modules["resource"] = unittest.mock.MagicMock()

# Automatically enable custom integrations defined in the test environment
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield