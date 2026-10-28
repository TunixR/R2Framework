from typing import Any

import pytest
from strands.hooks import BeforeModelCallEvent

from agent_tools.hooks import OMITTED_IMAGE_TEXT, MaxGuiImagesHook
from tests.unit.agent_tools._shared.fakes import FakeRegistry, is_bound_method_of


def _image() -> dict[str, Any]:
    return {"image": {"format": "jpeg", "source": {"bytes": b"screenshot"}}}


class _FakeAgent:
    def __init__(self, messages: list[dict[str, Any]]):
        self.messages = messages


class _FakeBeforeModelCallEvent:
    def __init__(self, messages: list[dict[str, Any]]):
        self.agent = _FakeAgent(messages)


def _run_hook(hook: MaxGuiImagesHook, messages: list[dict[str, Any]]) -> None:
    hook.limit_images(_FakeBeforeModelCallEvent(messages))  # pyright: ignore[reportArgumentType]


def test_register_hooks_adds_model_call_callback():
    registry = FakeRegistry()
    hook = MaxGuiImagesHook(max_images=2)

    hook.register_hooks(registry)  # pyright: ignore[reportArgumentType]

    assert len(registry.callbacks) == 1
    event_type, callback = registry.callbacks[0]
    assert event_type is BeforeModelCallEvent
    assert is_bound_method_of(hook, callback)


def test_negative_max_images_raises():
    with pytest.raises(ValueError):
        _ = MaxGuiImagesHook(max_images=-1)


def test_keeps_only_the_last_images_across_messages():
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": "start"}, _image()]},
        {"role": "assistant", "content": [{"text": "ok"}]},
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "1",
                        "status": "success",
                        "content": [_image(), _image()],
                    }
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "toolResult": {
                        "toolUseId": "2",
                        "status": "success",
                        "content": [_image()],
                    }
                }
            ],
        },
    ]

    _run_hook(MaxGuiImagesHook(max_images=2), messages)

    assert messages[0]["content"][1] == {"text": OMITTED_IMAGE_TEXT}
    assert messages[2]["content"][0]["toolResult"]["content"][0] == {
        "text": OMITTED_IMAGE_TEXT
    }
    assert "image" in messages[2]["content"][0]["toolResult"]["content"][1]
    assert "image" in messages[3]["content"][0]["toolResult"]["content"][0]


def test_keeps_images_untouched_when_under_limit():
    first_image = _image()
    second_image = _image()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [first_image]},
        {"role": "user", "content": [{"toolResult": {"content": [second_image]}}]},
    ]

    _run_hook(MaxGuiImagesHook(max_images=2), messages)

    assert messages[0]["content"][0] is first_image
    assert messages[1]["content"][0]["toolResult"]["content"][0] is second_image


def test_zero_max_images_replaces_all_images():
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [_image(), {"text": "keep me"}]},
        {
            "role": "user",
            "content": [{"toolResult": {"content": [_image(), {"text": "also keep"}]}}],
        },
    ]

    _run_hook(MaxGuiImagesHook(max_images=0), messages)

    assert messages[0]["content"][0] == {"text": OMITTED_IMAGE_TEXT}
    assert messages[0]["content"][1] == {"text": "keep me"}
    assert messages[1]["content"][0]["toolResult"]["content"][0] == {
        "text": OMITTED_IMAGE_TEXT
    }
    assert messages[1]["content"][0]["toolResult"]["content"][1] == {
        "text": "also keep"
    }


def test_text_only_messages_are_untouched():
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"text": "hello"}]},
        {"role": "assistant", "content": [{"text": "hi"}]},
    ]

    _run_hook(MaxGuiImagesHook(max_images=1), messages)

    assert messages == [
        {"role": "user", "content": [{"text": "hello"}]},
        {"role": "assistant", "content": [{"text": "hi"}]},
    ]
