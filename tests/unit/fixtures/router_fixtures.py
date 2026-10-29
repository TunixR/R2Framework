from collections.abc import Callable

import pytest
from sqlmodel import Session

from database.provider.models import Router


@pytest.fixture
def make_router(session: Session) -> Callable[..., Router]:
    """Return a factory that persists a router, defaulting to text-only."""

    def _make_router(
        *,
        capabilities: list[Router.Capability] | None = None,
        vision_backbone: Router.VisionBackbone | None = None,
        model_name: str = "gpt-4o-mini",
        api_endpoint: str = "https://example.test/v1",
        provider_type: Router.Provider = Router.Provider.OPENAI,
        api_key: str = "test-api-key",
        persist: bool = True,
    ) -> Router:
        router = Router(
            api_key=api_key,
            model_name=model_name,
            api_endpoint=api_endpoint,
            provider_type=provider_type,
            capabilities=capabilities or [Router.Capability.TEXT],
            vision_backbone=vision_backbone,
        )

        if persist:
            session.add(router)
            session.commit()
            session.refresh(router)
        return router

    return _make_router


@pytest.fixture
def mock_router(make_router: Callable[..., Router]) -> Router:
    return make_router()


@pytest.fixture
def mock_vision_router(make_router: Callable[..., Router]) -> Router:
    return make_router(
        capabilities=[Router.Capability.TEXT, Router.Capability.VISION],
    )
