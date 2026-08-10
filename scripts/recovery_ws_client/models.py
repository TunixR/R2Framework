from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(slots=True)
class TranscriptEvent:
    ts: str
    direction: str
    event_type: str
    payload: dict[str, Any] | str | None = None

    @classmethod
    def create(
        cls,
        *,
        direction: str,
        event_type: str,
        payload: dict[str, Any] | str | None = None,
    ) -> "TranscriptEvent":
        return cls(
            ts=utc_now_iso(),
            direction=direction,
            event_type=event_type,
            payload=payload,
        )


@dataclass(slots=True)
class ActionResult:
    success: bool
    action_type: str
    error: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload = {"success": self.success, "action_type": self.action_type}
        if self.error:
            payload["error"] = self.error
        return payload


@dataclass(slots=True)
class RunSummary:
    terminal_type: str = ""
    recovery_id: str | None = None
    actions_success: int = 0
    actions_failed: int = 0
    actions_received: int = 0


@dataclass(slots=True)
class RunTranscript:
    events: list[TranscriptEvent] = field(default_factory=list)
    summary: RunSummary = field(default_factory=RunSummary)

    def add(self, event: TranscriptEvent) -> None:
        self.events.append(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [asdict(e) for e in self.events],
            "summary": asdict(self.summary),
        }
