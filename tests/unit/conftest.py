"""
Pytest configuration for unit tests.

This module imports all fixtures from the conftest package to make them
available to all tests in the tests/unit directory.
"""

# Import all fixtures from the conftest package modules
pytest_plugins = [
    "tests.unit.conftest",
    "tests.unit.conftest.session_fixture",
    "tests.unit.conftest.auth_fixtures",
    "tests.unit.conftest.mock_s3_client_fixture",
    "tests.unit.conftest.mock_strands_model_fixture",
]
