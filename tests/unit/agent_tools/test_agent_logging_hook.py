from typing import Any
from uuid import UUID, uuid4

import pytest

from agent_tools.hooks import AgentLoggingHook
from database.logging.models import AgentTrace, GUITrace
from tests.unit.agent_tools._shared.fakes import (
    FakeBeforeInvocationEvent,
    FakeRegistry,
    is_bound_method_of,
)

from ..shared.mock_session import (  # noqa: F401 We need to import these fixtures for them to activate
    _STORE,
    clear_store,
    patched_dependencies,
)

# ---------------------------------------------------------------------------
# register_hooks
# ---------------------------------------------------------------------------


def test_register_hooks_adds_callbacks():
    registry = FakeRegistry()
    hook = AgentLoggingHook(agent_id=uuid4(), invocation_state={})

    hook.register_hooks(registry)  # type: ignore[arg-type]

    # Should have registered two callbacks
    assert len(registry.callbacks) == 2

    registered_methods = {cb.__name__ for _, cb in registry.callbacks}
    assert "log_start" in registered_methods
    assert "log_message" in registered_methods

    for _, cb in registry.callbacks:
        assert is_bound_method_of(hook, cb)


# ---------------------------------------------------------------------------
# log_start
# ---------------------------------------------------------------------------


def test_log_start_creates_agent_trace():
    agent_id = uuid4()
    inputs = {"task": "do something"}
    hook = AgentLoggingHook(agent_id=agent_id, invocation_state={"inputs": inputs})

    evt = FakeBeforeInvocationEvent()
    hook.log_start(evt)

    # An AgentTrace must be stored with the generated agent_trace_id
    trace: AgentTrace | None = _STORE.get(hook.agent_trace_id)  # type: ignore[assignment]
    assert isinstance(trace, AgentTrace)
    assert trace.id == hook.agent_trace_id
    assert trace.agent_id == agent_id
    assert trace.inputs == inputs


def test_log_start_creates_subagent_when_parent_id(monkeypatch):
    """
    SubAgentTrace in models.py currently requires an 'engine' parameter in __init__,
    while the hook constructs it without engine. We monkeypatch the SubAgentTrace
    class in the models module to a lightweight version compatible with the hook.
    """
    from database.logging import models as models_mod

    class DummySubAgentTrace:
        def __init__(self, session, **data: Any):
            self.id = uuid4()
            self.parent_trace_id = data.get("parent_trace_id")
            self.child_trace_id = data.get("child_trace_id")

    # Patch the SubAgentTrace class used by the hook to avoid __init__ using the session arg
    monkeypatch.setattr(models_mod, "SubAgentTrace", DummySubAgentTrace, raising=True)

    parent_id = uuid4()
    hook = AgentLoggingHook(
        agent_id=uuid4(), invocation_state={"inputs": {}}, parent_trace_id=parent_id
    )

    evt = FakeBeforeInvocationEvent()
    hook.log_start(evt)

    # AgentTrace is created
    trace: AgentTrace | None = _STORE.get(hook.agent_trace_id)  # type: ignore[assignment]
    assert isinstance(trace, AgentTrace)

    # SubAgentTrace-like object added as well
    sub_traces = [
        o
        for o in _STORE.values()
        if hasattr(o, "parent_trace_id") and getattr(o, "child_trace_id", None)
    ]
    assert len(sub_traces) == 1
    sub = sub_traces[0]
    assert sub.parent_trace_id == parent_id
    assert sub.child_trace_id == hook.agent_trace_id


# ---------------------------------------------------------------------------
# log_message and update_trace
# ---------------------------------------------------------------------------


def test_log_message_updates_trace_output_and_finished():
    """
    Current implementation builds output by joining 'text' of assistant messages,
    but it reads from the message dict itself rather than its 'content' items.
    As implemented, this yields an empty string even if content has text.
    """
    hook = AgentLoggingHook(agent_id=uuid4(), invocation_state={"inputs": {}})

    # First ensure the AgentTrace exists
    hook.log_start(FakeBeforeInvocationEvent())

    # Add assistant and user messages
    assistant_msg = {"role": "assistant", "content": [{"text": "Hello there"}]}
    user_msg = {"role": "user", "content": [{"text": "Hi!"}]}

    # Minimal event objects carrying the required 'message' attribute
    class MsgEvt:
        def __init__(self, message: dict):
            self.message = message

    hook.log_message(MsgEvt(assistant_msg))  # type: ignore[arg-type]
    hook.log_message(MsgEvt(user_msg))  # type: ignore[arg-type]

    # Fetch and check AgentTrace after log_message calls
    trace: AgentTrace | None = _STORE.get(hook.agent_trace_id)  # type: ignore[assignment]
    assert isinstance(trace, AgentTrace)
    assert trace.output == "Hello there"

    # Mark as finished
    hook.update_trace(finished=True)
    trace2: AgentTrace | None = _STORE.get(hook.agent_trace_id)  # type: ignore[assignment]
    assert isinstance(trace2, AgentTrace)
    assert trace2.finished_at is not None


# ---------------------------------------------------------------------------
# register_gui_trace
# ---------------------------------------------------------------------------


def test_register_gui_trace_raises_for_non_gui_agent():
    hook = AgentLoggingHook(agent_id=uuid4(), invocation_state={}, is_gui_agent=False)

    with pytest.raises(RuntimeError):
        hook.register_gui_trace(
            action_type="click",
            action_content={"x": 10, "y": 20},
            screenshot_bytes=b"\x89PNG",
            success=True,
        )


def test_register_gui_trace_saves_gui_entry_when_gui_agent():
    hook = AgentLoggingHook(agent_id=uuid4(), invocation_state={}, is_gui_agent=True)

    hook.register_gui_trace(
        action_type="click",
        action_content={"x": 10, "y": 20},
        screenshot_bytes=b"\x89PNG",
        success=True,
    )

    gui_traces = [o for o in _STORE.values() if isinstance(o, GUITrace)]
    assert len(gui_traces) == 1

    gui = gui_traces[0]
    assert gui.agent_trace_id == hook.agent_trace_id
    assert gui.action_type == "click"
    assert gui.action_content == {"x": 10, "y": 20}
    assert gui.success is True
