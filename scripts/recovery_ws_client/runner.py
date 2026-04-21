from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pyautogui
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from .actions import execute_action
from .config import ClientConfig
from .logging import write_transcript
from .models import RunTranscript, TranscriptEvent
from .protocol import message_type, parse_message
from .screenshots import capture_screenshot_bytes


class RecoveryWsRunner:
    def __init__(self, config: ClientConfig, payload: dict[str, Any]):
        self.config = config
        self.payload = payload
        self.transcript = RunTranscript()
        self.action_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.stop_event = asyncio.Event()
        self.next_action_at = datetime.now(tz=timezone.utc)
        self.actions_executed = 0

    async def _action_worker(self, websocket) -> None:  # pyright: ignore[reportMissingParameterType]
        while not self.stop_event.is_set():
            try:
                message = await asyncio.wait_for(self.action_queue.get(), timeout=0.2)
            except TimeoutError:
                continue

            now = datetime.now(tz=timezone.utc)
            remaining = (self.next_action_at - now).total_seconds()
            if remaining > 0:
                await asyncio.sleep(remaining)

            action = message.get("content")
            if not isinstance(action, dict):
                result_payload = {
                    "success": False,
                    "action_type": "unknown",
                    "error": "Invalid action content",
                }
            else:
                result = execute_action(action, dry_run=self.config.dry_run_actions)
                result_payload = result.as_payload()

                if result.success:
                    self.transcript.summary.actions_success += 1
                else:
                    self.transcript.summary.actions_failed += 1

            self.actions_executed += 1
            if (
                self.config.max_actions is not None
                and self.actions_executed >= self.config.max_actions
            ):
                self.stop_event.set()

            await websocket.send(json.dumps(result_payload))
            self.transcript.add(
                TranscriptEvent.create(
                    direction="outbound",
                    event_type="action_result",
                    payload=result_payload,
                )
            )

            self.next_action_at = datetime.now(tz=timezone.utc) + timedelta(
                seconds=self.config.action_delay_seconds
            )

    async def run(self) -> int:
        pyautogui.FAILSAFE = True

        try:
            async with connect(
                self.config.ws_url,
                additional_headers={"X-ROBOT-KEY": self.config.robot_key},
                max_size=None,
            ) as websocket:
                await websocket.send(json.dumps(self.payload))
                self.transcript.add(
                    TranscriptEvent.create(
                        direction="outbound",
                        event_type="initial_payload",
                        payload={"payload_id": self.config.payload_id},
                    )
                )

                worker = asyncio.create_task(self._action_worker(websocket))

                while not self.stop_event.is_set():
                    raw = await websocket.recv()
                    if not isinstance(raw, str):
                        continue

                    message = parse_message(raw)
                    msg_type = message_type(message)

                    self.transcript.add(
                        TranscriptEvent.create(
                            direction="inbound",
                            event_type=msg_type or "unknown",
                            payload=message,
                        )
                    )

                    if msg_type == "ping":
                        continue

                    if msg_type == "screenshot":
                        screenshot = capture_screenshot_bytes(
                            save_dir=self.config.save_screenshots_dir
                        )
                        await websocket.send(screenshot)
                        self.transcript.add(
                            TranscriptEvent.create(
                                direction="outbound",
                                event_type="screenshot_bytes",
                                payload={"bytes": len(screenshot)},
                            )
                        )
                        continue

                    if msg_type == "action":
                        self.transcript.summary.actions_received += 1
                        await self.action_queue.put(message)
                        continue

                    if msg_type == "done":
                        self.transcript.summary.terminal_type = "done"
                        recovery_id = message.get("id")
                        if isinstance(recovery_id, str):
                            self.transcript.summary.recovery_id = recovery_id
                        self.stop_event.set()
                        break

                    if msg_type == "error":
                        self.transcript.summary.terminal_type = "error"
                        self.stop_event.set()
                        break

                self.stop_event.set()
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)

            if self.config.log_json is not None:
                write_transcript(self.config.log_json, self.transcript)

            return 0 if self.transcript.summary.terminal_type == "done" else 1

        except ConnectionClosed as exc:
            self.transcript.summary.terminal_type = "disconnect"
            self.transcript.add(
                TranscriptEvent.create(
                    direction="internal",
                    event_type="connection_closed",
                    payload=str(exc),
                )
            )
            if self.config.log_json is not None:
                write_transcript(self.config.log_json, self.transcript)
            return 2
        except Exception as exc:
            self.transcript.summary.terminal_type = "exception"
            self.transcript.add(
                TranscriptEvent.create(
                    direction="internal",
                    event_type="exception",
                    payload=str(exc),
                )
            )
            if self.config.log_json is not None:
                write_transcript(self.config.log_json, self.transcript)
            return 3
