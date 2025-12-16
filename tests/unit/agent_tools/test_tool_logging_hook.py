import sys
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from strands.types.tools import ToolResult

from agent_tools.hooks import ToolLoggingHook
from database.logging.models import ToolTrace
from tests.unit.agent_tools._shared.fakes import (
    FakeAfterToolCallEvent,
    FakeBeforeToolCallEvent,
)

from ..shared.mock_session import (  # noqa: F401 We need to import these fixtures for them to activate
    _STORE,
    clear_store,
    patched_dependencies,
)


def test_log_tool_call_inserts_trace_for_tracked_tool():
    agent_trace_id = uuid4()
    tool_id = uuid4()
    tools = {"my_tool": tool_id}
    hook = ToolLoggingHook(agent_trace_id=agent_trace_id, tools=tools)

    evt = FakeBeforeToolCallEvent("my_tool", input_value={"key": "val"})
    hook.log_tool_call(evt)

    # trace_id should be set
    assert isinstance(hook.trace_id, UUID)

    # After logging the response (which fetches and updates the trace),
    # the trace should be retrievable in the spy store.
    resp_evt = FakeAfterToolCallEvent(
        "my_tool",
        exception=None,
        result={"status": "success", "content": [], "toolUseId": ""},
    )
    hook.log_tool_response(resp_evt)

    trace_obj = _STORE.get(hook.trace_id)
    assert isinstance(trace_obj, ToolTrace)
    assert trace_obj.agent_trace_id == agent_trace_id
    assert trace_obj.tool_id == tool_id
    assert trace_obj.input == {"key": "val"}


def test_log_tool_call_ignored_for_untracked_tool():
    agent_trace_id = uuid4()
    tools = {"tracked_tool": uuid4()}
    hook = ToolLoggingHook(agent_trace_id=agent_trace_id, tools=tools)

    evt = FakeBeforeToolCallEvent("other_tool", input_value="ignored")
    hook.log_tool_call(evt)

    # No trace should be created and no trace_id set
    assert not hasattr(hook, "trace_id")
    assert len(_STORE) == 0


def test_log_tool_response_success_updates_trace():
    agent_trace_id = uuid4()
    tool_id = uuid4()
    hook = ToolLoggingHook(agent_trace_id=agent_trace_id, tools={"tool_x": tool_id})

    call_evt = FakeBeforeToolCallEvent("tool_x", input_value="input-str")
    hook.log_tool_call(call_evt)

    result: ToolResult = {
        "status": "success",
        "content": [{"text": "result text"}],
        "toolUseId": "",
    }
    resp_evt = FakeAfterToolCallEvent("tool_x", exception=None, result=result)
    hook.log_tool_response(resp_evt)

    trace_obj = _STORE.get(hook.trace_id)
    assert isinstance(trace_obj, ToolTrace)
    assert trace_obj.success is True
    assert trace_obj.output == "result text"
    assert trace_obj.finished_at is not None


def test_log_tool_response_failure_updates_trace_with_exception():
    agent_trace_id = uuid4()
    tool_id = uuid4()
    hook = ToolLoggingHook(agent_trace_id=agent_trace_id, tools={"tool_y": tool_id})

    call_evt = FakeBeforeToolCallEvent("tool_y", input_value={"param": 1})
    hook.log_tool_call(call_evt)

    resp_evt = FakeAfterToolCallEvent(
        "tool_y", exception=RuntimeError("boom"), result=None
    )
    hook.log_tool_response(resp_evt)

    trace_obj = _STORE.get(hook.trace_id)
    assert isinstance(trace_obj, ToolTrace)
    assert trace_obj.success is False
    assert "boom" in (trace_obj.output or "")
    assert trace_obj.finished_at is not None
