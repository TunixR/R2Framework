"""
Pytest configuration for unit tests.

This module imports all fixtures from the conftest package to make them
available to all tests in the tests/unit directory.
"""

# Import all fixtures from the conftest package modules
pytest_plugins = [
    "tests.unit.fixtures",
    "tests.unit.fixtures.session_fixture",
    "tests.unit.fixtures.client_fixture",
    "tests.unit.fixtures.auth_fixtures",
    "tests.unit.fixtures.mock_s3_client_fixture",
    "tests.unit.fixtures.mock_strands_model_fixture",
]
