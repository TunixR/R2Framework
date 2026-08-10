from __future__ import annotations

import json
from pathlib import Path

from .models import RunTranscript


def write_transcript(path: Path, transcript: RunTranscript) -> None:
    print(f"Writing transcript to {path}...")
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(transcript.to_dict(), indent=2), encoding="utf-8")
