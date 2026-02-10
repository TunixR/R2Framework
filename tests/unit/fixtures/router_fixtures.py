import pytest
from sqlmodel import Session

from database.provider.models import Router


@pytest.fixture
def mock_router(session: Session) -> Router:
    router = Router(
        api_key="test-api-key",
        model_name="gpt-4o-mini",
        api_endpoint="https://example.test/v1",
        provider_type=Router.Provider.OPENAI,
    )
    session.add(router)
    session.commit()
    session.refresh(router)
    return router
