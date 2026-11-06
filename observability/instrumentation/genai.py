"""GenAI spans in the shape SigNoz reads: conversations, reasoning parts and tokens.

SigNoz builds its conversation view from the ``gen_ai.input.messages`` and
``gen_ai.output.messages`` span *attributes* of the latest GenAI semantic
conventions, and its token breakdown from ``gen_ai.usage.*``. Out of the box,
Strands writes the conversation as legacy span events, names reasoning parts
after its own content block (``reasoningContent``) and drops reasoning tokens.
This module closes those three gaps without changing what Strands records.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, override

from opentelemetry import trace
from strands.models.openai import OpenAIModel
from strands.telemetry import tracer as strands_tracer

from observability import attributes as attrs

if TYPE_CHECKING:
    from strands.types.content import ContentBlock
    from strands.types.interrupt import InterruptResponseContent
    from strands.types.streaming import StreamEvent

SEMCONV_OPT_IN_ENV = "OTEL_SEMCONV_STABILITY_OPT_IN"
# Latest conventions, with messages as span attributes instead of span events.
STRANDS_SEMCONV_OPT_IN = ("gen_ai_latest_experimental", "gen_ai_span_attributes_only")


class GenAITracer(strands_tracer.Tracer):
    """Strands tracer whose message parts use the semantic-convention part types."""

    @override
    def _map_content_blocks_to_otel_parts(
        self, content_blocks: list[ContentBlock] | list[InterruptResponseContent]
    ) -> list[dict[str, Any]]:
        return [
            _reasoning_part(part)
            for part in super()._map_content_blocks_to_otel_parts(content_blocks)
        ]


def _reasoning_part(part: dict[str, Any]) -> dict[str, Any]:
    """``{"type": "reasoningContent", ...}`` -> ``{"type": "reasoning", "content": text}``."""
    if part.get("type") != "reasoningContent":
        return part
    content = part.get("content")
    reasoning = content.get("reasoningText") if isinstance(content, dict) else None
    text = reasoning.get("text") if isinstance(reasoning, dict) else None
    return {"type": "reasoning", "content": text if isinstance(text, str) else ""}


def install_genai_tracer() -> None:
    """Opt Strands into the latest conventions and make it use ``GenAITracer``.

    Call it after the global tracer provider is set and before agents are
    created: Strands reads both when its tracer is built, and each agent keeps
    the tracer it was created with. Opt-in tokens already set are kept.
    """
    tokens = [
        token.strip()
        for token in os.environ.get(SEMCONV_OPT_IN_ENV, "").split(",")
        if token.strip()
    ]
    tokens += [token for token in STRANDS_SEMCONV_OPT_IN if token not in tokens]
    os.environ[SEMCONV_OPT_IN_ENV] = ",".join(tokens)
    # Strands keeps one module-level tracer, returned by ``get_tracer()``.
    strands_tracer._tracer_instance = GenAITracer()  # pyright: ignore[reportPrivateUsage]


class TracedOpenAIModel(OpenAIModel):
    """``OpenAIModel`` that also reports reasoning tokens on the ``chat`` span.

    Strands' ``Usage`` has no reasoning field, so the count the provider sends
    in ``usage.completion_tokens_details.reasoning_tokens`` is lost. The usage
    chunk is formatted while the model call's ``chat`` span is current.
    """

    @override
    def format_chunk(self, event: dict[str, Any], **kwargs: Any) -> StreamEvent:
        if event.get("chunk_type") == "metadata":
            record_reasoning_tokens(event.get("data"))
        return super().format_chunk(event, **kwargs)


def record_reasoning_tokens(usage: Any) -> None:
    """Set ``gen_ai.usage.reasoning.output_tokens`` on the current span, if reported."""
    details = getattr(usage, "completion_tokens_details", None)
    tokens = getattr(details, "reasoning_tokens", None)
    if isinstance(tokens, int) and not isinstance(tokens, bool):
        trace.get_current_span().set_attribute(
            attrs.GEN_AI_USAGE_REASONING_OUTPUT_TOKENS, tokens
        )
