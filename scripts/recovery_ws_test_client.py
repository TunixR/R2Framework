from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from scripts.recovery_ws_client import ClientConfig, RecoveryWsRunner
from scripts.recovery_ws_client.payloads import load_payload_by_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone recovery websocket test client"
    )
    _ = parser.add_argument("--ws-url", required=True)
    _ = parser.add_argument("--robot-key", required=True)
    _ = parser.add_argument("--payload-id", type=int, required=True)
    _ = parser.add_argument(
        "--payload-file",
        default="scripts/data/payloads.json",
    )
    _ = parser.add_argument("--action-delay-seconds", type=float, default=1.0)
    _ = parser.add_argument("--max-actions", type=int, default=None)
    _ = parser.add_argument("--dry-run-actions", action="store_true")
    _ = parser.add_argument("--log-json", default=None)
    _ = parser.add_argument("--save-screenshots-dir", default=None)
    return parser


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

        try:
            payload = load_payload_by_id(
                payload_file=payload_file, payload_id=args.payload_id
            )
        except ValueError as exc:
            print(f"Payload error: {exc}", file=sys.stderr)
            return 2

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
        )

        runner = RecoveryWsRunner(config=config, payload=payload)
        status = asyncio.run(runner.run())

        summary = runner.transcript.summary
        print(
            "terminal=",
            summary.terminal_type,
            "actions_received=",
            summary.actions_received,
            "actions_success=",
            summary.actions_success,
            "actions_failed=",
            summary.actions_failed,
            "recovery_id=",
            summary.recovery_id,
        )
        return status
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    status = main()
    print(f"Program exited with status: {status}")
