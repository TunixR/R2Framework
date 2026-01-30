import sys
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

# Global in-memory store to simulate persistence across Session instances
_STORE: dict[UUID, Any] = {}


class MockSession:
    """
    Spy replacement for sqlmodel.Session that records added objects in memory and
    supports retrieval via get(model_class, id) without touching a real database.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        self.added: list[Any] = []
        self.commit_count: int = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # pyright: ignore[reportMissingParameterType]
        return False

    def add(self, obj: Any):
        self.added.append(obj)
        _STORE[obj.id] = obj

    def commit(self):
        self.commit_count += 1

    def exec(self, _query: Any):
        raise NotImplementedError(
            "MockSession.exec is not implemented. You must spy on it to change behavior during testing."
        )

    def get(self, _, id: UUID):
        return _STORE.get(id)

    def refresh(self, _: Any):
        pass


@pytest.fixture(autouse=True)
def patched_dependencies(monkeypatch):  # pyright: ignore[reportMissingParameterType]
    """
    Patch dependencies used by AgentLoggingHook so no real DB is touched:
    - Patch Session inside agent_tools.hooks to MockSession
    - Optionally patch database.general.general_engine to a dummy object (ignored by MockSession)
    """
    import agent_tools.hooks as hooks_mod

    # Patch Session to our spy
    monkeypatch.setattr(hooks_mod, "Session", MockSession, raising=True)
    # Provide a dummy general_engine; MockSession ignores it
    dummy_general_mod = SimpleNamespace(general_engine=object())
    monkeypatch.setitem(sys.modules, "database.general", dummy_general_mod)

    return {"hooks_mod": hooks_mod, "general_mod": dummy_general_mod}


@pytest.fixture(autouse=True)
def clear_store():
    """
    Ensure the in-memory store is clean for each test.
    """
    _STORE.clear()
    yield
    _STORE.clear()
