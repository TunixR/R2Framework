from __future__ import annotations

import numpy
import argparse
import subprocess
import sys
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run recovery evaluation against the FastAPI framework"
    )
    _ = parser.add_argument(
        "--payload",
        required=True,
        help="Path to payloads JSON file",
    )
    _ = parser.add_argument(
        "--ground-truth",
        required=True,
        help="Path to ground truth JSON file",
    )
    _ = parser.add_argument(
        "--payload-id",
        type=int,
        default=1,
        help="Payload ID to evaluate (1-based index, default: 1)",
    )
    _ = parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the FastAPI server (default: 127.0.0.1)",
    )
    _ = parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the FastAPI server (default: 8000)",
    )
    _ = parser.add_argument(
        "--robot-key",
        default="",
        help="Robot key for authentication (leave blank for eval)",
    )
    _ = parser.add_argument(
        "--log-json",
        default=None,
        help="Path to write the debug log JSON",
    )
    _ = parser.add_argument(
        "--startup-timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for the server to start (default: 30)",
    )
    _ = parser.add_argument(
        "--action-delay-seconds",
        type=float,
        default=1.0,
        help="Delay between actions in seconds (default: 1.0)",
    )
    _ = parser.add_argument(
        "--max-actions",
        type=int,
        default=None,
        help="Maximum number of actions to execute",
    )
    _ = parser.add_argument(
        "--dry-run-actions",
        action="store_true",
        help="Dry run actions without executing them",
    )
    return parser


def wait_for_server(host: str, port: int, _timeout: float) -> bool:
    import urllib.request
    import urllib.error

    url = f"http://{host}:{port}/scalar"
    while time.monotonic() < numpy.inf:  # Sorry
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    payload_path = Path(args.payload).resolve()
    ground_truth_path = Path(args.ground_truth).resolve()

    if not payload_path.exists():
        print(f"Payload file not found: {payload_path}", file=sys.stderr)
        return 2
    if not ground_truth_path.exists():
        print(f"Ground truth file not found: {ground_truth_path}", file=sys.stderr)
        return 2

    server_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        cwd=str(Path(__file__).resolve().parent.parent),
        # stdout=subprocess.PIPE,
        # stderr=subprocess.PIPE,
    )

    try:
        print(f"Waiting for server on {args.host}:{args.port}...")
        if not wait_for_server(args.host, args.port, args.startup_timeout):
            print("Server failed to start within timeout", file=sys.stderr)
            server_proc.terminate()
            server_proc.wait(timeout=5)
            return 3
        print("Server is ready.")

        ws_url = f"ws://{args.host}:{args.port}/evals/recovery/ws"

        client_cmd = [
            "C:\\Code\\R2Framework\\backend\\.venv\\Scripts\\python.exe",
            "-m",
            "scripts.recovery_ws_test_client",
            "--ws-url",
            ws_url,
            "--robot-key",
            args.robot_key or "eval-key",
            "--payload-id",
            str(args.payload_id),
            "--payload-file",
            str(payload_path),
            "--ground-truth-file",
            str(ground_truth_path),
            "--eval",
            "--action-delay-seconds",
            str(args.action_delay_seconds),
        ]
        if args.log_json:
            client_cmd.extend(["--log-json", args.log_json])
        if args.max_actions is not None:
            client_cmd.extend(["--max-actions", str(args.max_actions)])
        if args.dry_run_actions:
            client_cmd.append("--dry-run-actions")

        print(f"Running eval client: {' '.join(client_cmd)}")
        result = subprocess.run(
            client_cmd,
            cwd=str(Path(__file__).resolve().parent.parent),
            check=True,
            # capture_output=True,
            # text=True,
        )

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)

        return result.returncode
    finally:
        print("Shutting down server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server_proc.kill()
            server_proc.wait()
        print("Server stopped.")


if __name__ == "__main__":
    sys.exit(main())
