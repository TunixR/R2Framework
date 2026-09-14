from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from scripts.recovery_ws_client import ClientConfig, RecoveryWsRunner
from scripts.recovery_ws_client.payloads import load_payload_by_id

import traceback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone recovery websocket test client"
    )
    _ = parser.add_argument("--ws-url", required=True)
    _ = parser.add_argument("--robot-key", required=True)
    _ = parser.add_argument("--payload-id", type=int, required=True)
    _ = parser.add_argument(
        "--payload-file",
        default="evals/data/payloads.json",
    )
    _ = parser.add_argument("--action-delay-seconds", type=float, default=1.0)
    _ = parser.add_argument("--max-actions", type=int, default=None)
    _ = parser.add_argument("--dry-run-actions", action="store_true")
    _ = parser.add_argument("--log-json", default=None)
    _ = parser.add_argument("--save-screenshots-dir", default=None)
    _ = parser.add_argument(
        "--eval", action="store_true", help="Enable evaluation mode"
    )
    _ = parser.add_argument(
        "--ground-truth-file",
        default="evals/data/ground_truth.json",
        help="Ground truth JSON file for eval mode",
    )
    return parser


def load_recovery_task(ground_truth_file: Path, payload_id: int) -> str:
    if not ground_truth_file.exists():
        return ""
    try:
        raw = json.loads(ground_truth_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    if payload_id != -1:
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list) or payload_id < 1 or payload_id > len(raw):
            return ""
        entry = raw[payload_id - 1]
    else:
        entry = raw
    levels = entry.get("ground_truth_levels", {})
    return levels.get("moderate", "")


def main() -> int:
    try:
        parser = build_parser()
        args = parser.parse_args()

        if args.action_delay_seconds < 0:
            parser.error("--action-delay-seconds must be >= 0")

        payload_file = Path(args.payload_file)
        log_json = Path(args.log_json) if args.log_json else None
        save_screenshots_dir = (
            Path(args.save_screenshots_dir) if args.save_screenshots_dir else None
        )
        ground_truth_file = Path(args.ground_truth_file)

        try:
            payload = load_payload_by_id(
                payload_file=payload_file, payload_id=args.payload_id
            )
        except ValueError as exc:
            print(f"Payload error: {exc}", file=sys.stderr)
            return 2

        recovery_task = load_recovery_task(ground_truth_file, args.payload_id)

        config = ClientConfig(
            ws_url=args.ws_url,
            robot_key=args.robot_key,
            payload_file=payload_file,
            payload_id=args.payload_id,
            action_delay_seconds=args.action_delay_seconds,
            max_actions=args.max_actions,
            dry_run_actions=args.dry_run_actions,
            log_json=log_json,
            save_screenshots_dir=save_screenshots_dir,
            recovery_task=recovery_task,
            eval=args.eval,
            ground_truth_file=ground_truth_file,
        )

        runner = RecoveryWsRunner(config=config, payload=payload)
        status = asyncio.run(runner.run())

        summary = runner.transcript.summary
        run_output: dict[str, Any] = {
            "terminal": summary.terminal_type,
            "actions_received": summary.actions_received,
            "actions_success": summary.actions_success,
            "actions_failed": summary.actions_failed,
            "recovery_id": summary.recovery_id,
        }
        if runner.eval_result is not None:
            run_output["eval_result"] = runner.eval_result

        if config.log_json is not None:
            log_transcript = runner.transcript.to_dict()
            log_transcript["eval_result"] = runner.eval_result
            config.log_json.parent.mkdir(parents=True, exist_ok=True)
            config.log_json.write_text(
                json.dumps(log_transcript, indent=2), encoding="utf-8"
            )

        return status
    except Exception as _:
        print(f"Error: {traceback.format_exc()}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    status = main()
    print(f"Program exited with status: {status}")
