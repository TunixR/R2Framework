"""Fixtures for the SigNoz integration tests.

The suite needs a live SigNoz: the OTLP collector at
``settings.OTEL_EXPORTER_OTLP_ENDPOINT`` and its ClickHouse (see ``signoz.py``).
Without them every test is skipped. All telemetry is exported under a unique
``service.name`` and deleted again when the session ends.
"""

from __future__ import annotations

import logging
import socket
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import Any, override
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel import Session
from strands.models import Model

import settings
from database.engine import get_session
from observability import Observability, configure_observability
from observability.config import ObservabilitySettings
from observability.events import log_event
from routers.recovery import router as recovery_router
from tests.integration.observability.signoz import SignozClickHouse

# Unit fixtures reused for the recovery flow (in-memory SQLite, seed rows).
from tests.unit.fixtures.agent_fixtures import gateway_agent, make_agent  # noqa: F401
from tests.unit.fixtures.logging_fixtures import make_robot_key  # noqa: F401
from tests.unit.fixtures.payload_fixtures import valid_recovery_payload  # noqa: F401
from tests.unit.fixtures.router_fixtures import make_router, mock_router  # noqa: F401
from tests.unit.fixtures.session_fixture import (  # noqa: F401
    engine_fixture,
    session_fixture,
)

OTLP_ENDPOINT = settings.OTEL_EXPORTER_OTLP_ENDPOINT
SECRET = "sk-integrationsecret123"

logger = logging.getLogger("tests.integration.signoz")


@dataclass
class Telemetry:
    client: TestClient
    handle: Observability
    signoz: SignozClickHouse

    def flush(self) -> None:
        """Push everything buffered to the collector before polling SigNoz."""
        assert self.handle.tracer_provider is not None
        assert self.handle.logger_provider is not None
        self.handle.tracer_provider.force_flush()
        self.handle.logger_provider.force_flush()


class ScriptedModel(Model):
    """Strands model that answers with fixed text, so no LLM is called."""

    def __init__(self, text: str) -> None:
        self._text = text

    @override
    def update_config(self, **model_config: Any) -> None:
        return None

    @override
    def get_config(self) -> Any:
        return {}

    @override
    async def structured_output(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        output_model: type[BaseModel],
        prompt: Any,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError
        yield {}

    @override
    async def stream(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        messages: Any,
        tool_specs: Any = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": self._text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
        yield {
            "metadata": {
                "usage": {"inputTokens": 12, "outputTokens": 4, "totalTokens": 16},
                "metrics": {"latencyMs": 1},
            }
        }


def _collector_reachable() -> bool:
    url = urlparse(OTLP_ENDPOINT)
    try:
        with socket.create_connection(
            (url.hostname or "localhost", url.port or 4318), timeout=2
        ):
            return True
    except OSError:
        return False


def _routes(app: FastAPI) -> None:
    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str]:
        if item_id == "missing":
            raise HTTPException(status_code=404, detail="Item not found")
        return {"id": item_id}

    @app.get("/events")
    async def events() -> dict[str, str]:
        log_event(
            logger,
            "integration.checked",
            {
                "integration.note": f"api_key={SECRET}",
                "integration.count": 3,
                "integration.passed": True,
            },
            logging.WARNING,
        )
        return {"status": "logged"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(f"database password={SECRET} unreachable")

    app.include_router(recovery_router)


@pytest.fixture(scope="session")
def signoz() -> SignozClickHouse:
    client = SignozClickHouse(f"r2framework-it-{uuid.uuid4().hex[:12]}")
    if not _collector_reachable():
        pytest.skip(f"SigNoz collector not reachable at {OTLP_ENDPOINT}")
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "no SigNoz here"
        pytest.skip(f"SigNoz ClickHouse not reachable: {exc}")
    return client


@pytest.fixture(scope="session")
def telemetry(signoz: SignozClickHouse, session: Session) -> Iterator[Telemetry]:
    app = FastAPI()
    _routes(app)

    def _session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = _session
    # Global providers, so Strands' tracer exports into the same pipeline.
    handle = configure_observability(
        app,
        settings=ObservabilitySettings.from_settings(
            enabled=True,
            service_name=signoz.service_name,
            environment="integration-test",
            log_format="console",
        ),
    )
    try:
        yield Telemetry(client=TestClient(app), handle=handle, signoz=signoz)
    finally:
        handle.shutdown()
        signoz.wait_until_settled()
        signoz.delete_service_data()
        assert signoz.spans() == [], "integration spans were not cleaned up"
        assert signoz.logs() == [], "integration logs were not cleaned up"
