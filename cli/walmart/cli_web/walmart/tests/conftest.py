"""Pytest configuration — register custom markers and shared fixtures."""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Fast unit tests (mocked HTTP, no network)")
    config.addinivalue_line("markers", "live: Live API tests that hit the real API")
    config.addinivalue_line("markers", "subprocess: Subprocess tests that invoke the installed CLI binary")


@pytest.fixture(autouse=True, scope="function")
def close_client_before_subprocess(request):
    """Close the shared playwright context before subprocess tests.

    Subprocess tests spawn new cli-web-walmart processes that open Chrome.
    Chrome refuses to open if the profile is already in use by the test process.
    This fixture ensures the in-process client is closed before each subprocess test.
    """
    if request.node.get_closest_marker("subprocess"):
        # Close any open playwright context so subprocess tests can use the profile
        try:
            from cli_web.walmart.core import client as _client
            _client.close_context()
        except Exception:
            pass
    yield
    # No teardown needed — subprocess tests don't open in-process contexts
