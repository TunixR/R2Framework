from agent_tools.hooks import LimitToolCounts
from tests.agent_tools._shared.fakes import (
    FakeAfterToolCallEvent,
    FakeBeforeInvocationEvent,
    FakeBeforeToolCallEvent,
    FakeRegistry,
    is_bound_method_of,
    make_validation_error,
)

# ---------------------------------------------------------------------------
# Tests: register_hooks
# ---------------------------------------------------------------------------


def test_register_hooks_adds_callbacks():
    registry = FakeRegistry()
    hooks = LimitToolCounts(max_tool_counts={"tool_a": 1})

    hooks.register_hooks(registry)  # type: ignore[arg-type]

    # Should have registered three callbacks
    assert len(registry.callbacks) == 3

    # Validate the callbacks are bound methods of the instance
    registered_methods = {cb.__name__ for _, cb in registry.callbacks}
    assert "reset_counts" in registered_methods
    assert "intercept_tool" in registered_methods
    assert "intercept_response" in registered_methods

    # Ensure they are bound to the same hooks instance (method __self__)
    for _, cb in registry.callbacks:
        assert is_bound_method_of(hooks, cb)


# ---------------------------------------------------------------------------
# Tests: throttling logic
# ---------------------------------------------------------------------------


def test_intercept_tool_throttles_after_max():
    hooks = LimitToolCounts(max_tool_counts={"my_tool": 1})

    # First call: should be allowed
    evt1 = FakeBeforeToolCallEvent("my_tool")
    hooks.intercept_tool(evt1)
    assert not evt1.cancel_tool

    # Second call: should be throttled
    evt2 = FakeBeforeToolCallEvent("my_tool")
    hooks.intercept_tool(evt2)
    assert evt2.cancel_tool
    assert isinstance(evt2.cancel_tool, str)
    assert "invoked too many" in evt2.cancel_tool


def test_intercept_tool_no_limit_for_unspecified_tool():
    hooks = LimitToolCounts(max_tool_counts={"limited_tool": 1})

    # Tool not specified in max_tool_counts should not be limited
    for i in range(5):
        evt = FakeBeforeToolCallEvent("unlimited_tool")
        hooks.intercept_tool(evt)
        assert not evt.cancel_tool


def test_reset_counts_clears_state():
    hooks = LimitToolCounts(max_tool_counts={"a": 1})
    evt = FakeBeforeToolCallEvent("a")
    hooks.intercept_tool(evt)

    # Ensure count is recorded
    assert hooks.tool_counts.get("a", 0) == 1

    # Reset counts
    hooks.reset_counts(FakeBeforeInvocationEvent())
    assert hooks.tool_counts == {}


# ---------------------------------------------------------------------------
# Tests: decrement on exceptions in intercept_response
# ---------------------------------------------------------------------------


def test_intercept_response_decrements_on_validation_error():
    hooks = LimitToolCounts(max_tool_counts={"validate_tool": 2})

    # Simulate two calls recorded
    hooks.intercept_tool(FakeBeforeToolCallEvent("validate_tool"))
    hooks.intercept_tool(FakeBeforeToolCallEvent("validate_tool"))
    assert hooks.tool_counts.get("validate_tool", 0) == 2

    # ValidationError should decrement by one
    val_err = make_validation_error()
    hooks.intercept_response(FakeAfterToolCallEvent("validate_tool", val_err))
    assert hooks.tool_counts.get("validate_tool", 0) == 1


def test_intercept_response_decrements_on_type_error():
    hooks = LimitToolCounts(max_tool_counts={"type_tool": 2})

    # Record a single call
    hooks.intercept_tool(FakeBeforeToolCallEvent("type_tool"))
    assert hooks.tool_counts.get("type_tool", 0) == 1

    # TypeError should decrement by one (not below zero)
    hooks.intercept_response(FakeAfterToolCallEvent("type_tool", TypeError("bad arg")))
    assert hooks.tool_counts.get("type_tool", 0) == 0

    # Another decrement should not go negative
    hooks.intercept_response(FakeAfterToolCallEvent("type_tool", TypeError("another")))
    assert hooks.tool_counts.get("type_tool", 0) == 0


def test_intercept_response_does_not_decrement_on_other_exceptions():
    hooks = LimitToolCounts(max_tool_counts={"other_tool": 3})
    hooks.intercept_tool(FakeBeforeToolCallEvent("other_tool"))
    hooks.intercept_tool(FakeBeforeToolCallEvent("other_tool"))
    assert hooks.tool_counts.get("other_tool", 0) == 2

    # An exception that is neither ValidationError nor TypeError should not decrement
    hooks.intercept_response(FakeAfterToolCallEvent("other_tool", RuntimeError("oops")))
    assert hooks.tool_counts.get("other_tool", 0) == 2
