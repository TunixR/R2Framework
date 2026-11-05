"""Doubles for driving TooledGuiAgent without a robot, Postgres or an LLM."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, override
from uuid import uuid4

import pytest
from strands.hooks import HookProvider, HookRegistry

import database.agents.tooled_gui_agent as tooled_module
from database.agents.tooled_gui_agent import TooledGuiAgent
from tests.unit.shared.fake_websocket import FakeWebSocket, make_test_image_bytes
from tests.unit.shared.scripted_model import ScriptedModel, Turn


class FakeHook(HookProvider):
    """Stands in for AgentLoggingHook, which writes audit rows to Postgres."""

    def __init__(self, **_: Any) -> None:
        self.gui_traces: list[tuple[str, bool]] = []

    @override
    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        return None

    async def register_gui_trace(
        self,
        action_type: str,
        _content: Any,
        _screenshot: bytes,
        _started_at: Any,
        _finished_at: Any,
        success: bool = True,
    ) -> None:
        self.gui_traces.append((action_type, success))

    def update_trace(self, finished: bool = False, cost: float = 0.0) -> None:
        return None


def make_robot(*, action_success: bool = True) -> FakeWebSocket:
    """A robot that serves 64x48 screenshots and answers actions with ``action_success``."""
    screenshots = [make_test_image_bytes(size=(64, 48)) for _ in range(10)]
    return FakeWebSocket(screenshots, action_success=action_success)


def patch_gui_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the settle delay between actions and the audit rows."""

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(tooled_module, "AgentLoggingHook", FakeHook)
    monkeypatch.setattr(tooled_module, "asyncio", SimpleNamespace(sleep=_no_sleep))


def make_tooled_gui_agent(*turns: Turn) -> TooledGuiAgent:
    """A GUI agent whose inner Strands model plays ``turns``."""
    model = ScriptedModel(*turns)
    router = SimpleNamespace(
        relative_dim=False,
        original_coords=lambda x, y, _w, _h: [x, y],
        model_name="scripted",
        get_model=lambda: model,
    )
    agent = SimpleNamespace(id=uuid4(), prompt="{instruction}", router=router)
    return TooledGuiAgent(agent)  # pyright: ignore[reportArgumentType]


GUI_TASK_INPUT: dict[str, Any] = {
    "task": "Fill the invoice",
    "variables": {},
    "ui_log": [{}, {}],
    "errored_act": {"activity_id": 3},
    "model": "invoice-process",
}
