"""
Pytest fixture to patch strands.models.openai.OpenAIModel with a test double.

This allows tests to preload deterministic responses for code paths that would
otherwise call the OpenAI API.

Usage in tests:
    def test_something(fake_openai_model):
        # Preload responses (LIFO: last pushed is returned first)
        fake_openai_model.set_responses([
            {"choices": [{"message": {"content": "first"}}]},
            {"choices": [{"message": {"content": "second"}}]},
        ])

        # Code under test that constructs OpenAIModel() and calls call/invoke_async
        # will receive the above responses in reverse order (second, then first).

You can also push responses one-by-one using:
    fake_openai_model.push_response({...})

The fixture exposes the FakeOpenAIModel class so tests can inspect remaining
responses or clear them between steps.
"""

from typing import Any, List

import pytest


@pytest.fixture(autouse=False)
def fake_openai_model(monkeypatch):
    """
    Patch strands.models.openai.OpenAIModel to use tests.shared.fake_openai_model.FakeOpenAIModel.

    Returns the FakeOpenAIModel class so tests can preload responses via:
      - fake_openai_model.set_responses([...])
      - fake_openai_model.set_structured_outputs([...])
      - fake_openai_model.push_response(obj)
      - fake_openai_model.push_structured_output(obj)
      - fake_openai_model.clear_responses()
      - fake_openai_model.remaining()
      - fake_openai_model.remaining_structured_output()
    """
    import strands.models.openai as openai_mod

    from tests.shared.mock_strands_model import MockStrandsModel

    monkeypatch.setattr(openai_mod, "OpenAIModel", MockStrandsModel, raising=True)

    # Provide a convenient API to the test author via the fixture return value.
    # Expose some helpers directly for ease of use.
    class _FixtureAPI:
        Model = MockStrandsModel

        def set_responses(self, responses: List[Any]) -> None:
            MockStrandsModel.set_responses(responses)

        def set_structured_outputs(self, responses: List[Any]) -> None:
            MockStrandsModel.set_structured_outputs(responses)

        def push_response(self, response: Any) -> None:
            MockStrandsModel.push_response(response)

        def push_structured_output(self, response: Any) -> None:
            MockStrandsModel.push_structured_output(response)

        def clear_responses(self) -> None:
            MockStrandsModel.clear_responses()

        def remaining(self) -> int:
            return MockStrandsModel.remaining()

        def remaining_structured_outputs(self) -> int:
            return MockStrandsModel.remaining_structured_outputs()

    # Ensure a clean stack for each test that opts in to the fixture
    MockStrandsModel.clear_responses()

    return _FixtureAPI()
