#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


def parse_env_assignments(items: list[str]) -> dict[str, str]:
    env_vars: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid env assignment: {item}")
        key, value = item.split("=", 1)
        env_vars[key] = value
    return env_vars


class Client:
    def __init__(self, base_url: str, token: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = {"error": body}
            raise RuntimeError(f"{exc.code}: {payload.get('error', body)}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Login-node client for the Codex GPU bridge")
    parser.add_argument("--server", default=os.environ.get("GPU_AGENT_URL"))
    parser.add_argument("--token", default=os.environ.get("GPU_AGENT_TOKEN"))

    subparsers = parser.add_subparsers(dest="command_name", required=True)

    subparsers.add_parser("health")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--limit", type=int, default=20)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("run_id")

    logs_parser = subparsers.add_parser("logs")
    logs_parser.add_argument("run_id")
    logs_parser.add_argument("--follow", action="store_true")
    logs_parser.add_argument("--poll-interval", type=float, default=2.0)

    cancel_parser = subparsers.add_parser("cancel")
    cancel_parser.add_argument("run_id")

    wait_parser = subparsers.add_parser("wait")
    wait_parser.add_argument("run_id")
    wait_parser.add_argument("--poll-interval", type=float, default=2.0)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--cwd", default=os.getcwd())
    run_parser.add_argument("--conda-prefix")
    run_parser.add_argument("--conda-env", dest="conda_env_name")
    run_parser.add_argument("--module-setup", default="")
    run_parser.add_argument("--timeout-seconds", type=float)
    run_parser.add_argument("--env", action="append", default=[])
    run_parser.add_argument("command", nargs=argparse.REMAINDER)

    return parser


def require_server(args: argparse.Namespace) -> Client:
    if not args.server:
        raise SystemExit("Set --server or GPU_AGENT_URL")
    return Client(base_url=args.server, token=args.token)


def print_run_summary(run: dict[str, Any]) -> None:
    for key in ("run_id", "status", "exit_code", "host", "pid", "cwd", "conda_prefix", "conda_env_name", "started_at", "finished_at", "log_path"):
        if key in run:
            print(f"{key}: {run.get(key)}")


def handle_health(args: argparse.Namespace) -> int:
    client = require_server(args)
    payload = client.request("GET", "/health")
    print(json.dumps(payload, indent=2))
    return 0


def handle_list(args: argparse.Namespace) -> int:
    client = require_server(args)
    payload = client.request("GET", f"/runs?limit={args.limit}")
    for run in payload.get("runs", []):
        print(f"{run['run_id']}  {run['status']}  {run['cwd']}")
    return 0


def handle_status(args: argparse.Namespace) -> int:
    client = require_server(args)
    payload = client.request("GET", f"/runs/{args.run_id}")
    print_run_summary(payload)
    return 0


def handle_logs(args: argparse.Namespace) -> int:
    client = require_server(args)
    offset = 0
    while True:
        payload = client.request("GET", f"/runs/{args.run_id}/logs?offset={offset}")
        text = payload.get("text", "")
        if text:
            sys.stdout.write(text)
            sys.stdout.flush()
        offset = payload.get("next_offset", offset)
        if not args.follow or payload.get("complete"):
            break
        time.sleep(args.poll_interval)
    return 0


def handle_cancel(args: argparse.Namespace) -> int:
    client = require_server(args)
    payload = client.request("POST", f"/runs/{args.run_id}/cancel", payload={})
    print_run_summary(payload)
    return 0


def handle_wait(args: argparse.Namespace) -> int:
    client = require_server(args)
    while True:
        payload = client.request("GET", f"/runs/{args.run_id}")
        print(f"{payload['run_id']}  {payload['status']}")
        if payload["status"] in TERMINAL_STATES:
            return 0 if payload["status"] == "succeeded" else 1
        time.sleep(args.poll_interval)


def handle_run(args: argparse.Namespace) -> int:
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        raise SystemExit("Pass the command after `--`")

    client = require_server(args)
    payload = client.request(
        "POST",
        "/run",
        payload={
            "cwd": args.cwd,
            "conda_prefix": args.conda_prefix,
            "conda_env_name": args.conda_env_name,
            "module_setup": args.module_setup,
            "timeout_seconds": args.timeout_seconds,
            "env": parse_env_assignments(args.env),
            "command": shlex.join(args.command),
        },
    )
    print_run_summary(payload)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "health": handle_health,
        "list": handle_list,
        "status": handle_status,
        "logs": handle_logs,
        "cancel": handle_cancel,
        "wait": handle_wait,
        "run": handle_run,
    }

    try:
        return handlers[args.command_name](args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
