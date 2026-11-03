"""
Pytest configuration for unit tests.

This module imports all fixtures from the conftest package to make them
available to all tests in the tests/unit directory.
"""

import os

# Telemetry must be disabled before `main` is imported by fixtures, otherwise
# every test run would try to export OTLP data to localhost:4318.
# `OTEL_SDK_DISABLED` must stay unset: the OTel SDK turns every provider into a
# no-op when it is true, which would also disable the in-memory test providers.
os.environ["OBSERVABILITY_ENABLED"] = "false"
os.environ.pop("OTEL_SDK_DISABLED", None)

# Import all fixtures from the conftest package modules
pytest_plugins = [
    "tests.unit.fixtures",
    "tests.unit.fixtures.session_fixture",
    "tests.unit.fixtures.client_fixture",
    "tests.unit.fixtures.auth_fixtures",
    "tests.unit.fixtures.mock_s3_client_fixture",
    "tests.unit.fixtures.mock_strands_model_fixture",
    "tests.unit.fixtures.router_fixtures",
    "tests.unit.fixtures.tool_fixtures",
    "tests.unit.fixtures.agent_fixtures",
    "tests.unit.fixtures.payload_fixtures",
    "tests.unit.fixtures.logging_fixtures",
]
