#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def detect_conda_sh(explicit: str | None) -> str | None:
    if explicit:
        return explicit

    conda_exe = os.environ.get("CONDA_EXE")
    if conda_exe:
        candidate = Path(conda_exe).resolve().parent.parent / "etc" / "profile.d" / "conda.sh"
        if candidate.is_file():
            return str(candidate)

    for candidate in (
        Path.home() / "miniconda3" / "etc" / "profile.d" / "conda.sh",
        Path.home() / "anaconda3" / "etc" / "profile.d" / "conda.sh",
        Path("/opt/conda/etc/profile.d/conda.sh"),
    ):
        if candidate.is_file():
            return str(candidate)

    return None


@dataclass
class ActiveRun:
    process: subprocess.Popen[str]
    metadata_path: Path
    log_path: Path
    cancel_requested: bool = False


class RunManager:
    def __init__(self, state_dir: Path, conda_sh: str | None) -> None:
        self.state_dir = state_dir
        self.runs_dir = state_dir / "runs"
        self.logs_dir = state_dir / "logs"
        self.conda_sh = conda_sh
        self.lock = threading.Lock()
        self.active_runs: dict[str, ActiveRun] = {}

        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        entries = sorted(self.runs_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        return [read_json(path) for path in entries[:limit]]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        metadata_path = self.runs_dir / f"{run_id}.json"
        if not metadata_path.is_file():
            return None
        return read_json(metadata_path)

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("`command` must be a non-empty string")

        conda_prefix = payload.get("conda_prefix")
        conda_env_name = payload.get("conda_env_name")
        if conda_prefix and conda_env_name:
            raise ValueError("Specify only one of `conda_prefix` or `conda_env_name`")
        if (conda_prefix or conda_env_name) and not self.conda_sh:
            raise ValueError("Conda execution was requested but `conda.sh` could not be detected")

        cwd = str(Path(payload.get("cwd") or os.getcwd()).expanduser().resolve())
        env_vars = payload.get("env") or {}
        if not isinstance(env_vars, dict):
            raise ValueError("`env` must be a JSON object")

        module_setup = payload.get("module_setup") or ""
        timeout_seconds = payload.get("timeout_seconds")
        if timeout_seconds is not None and (not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0):
            raise ValueError("`timeout_seconds` must be a positive number")

        run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        metadata_path = self.runs_dir / f"{run_id}.json"
        command_script_path = self.runs_dir / f"{run_id}.command.sh"
        log_path = self.logs_dir / f"{run_id}.log"

        command_script_path.write_text(self._build_command_script(env_vars, module_setup, command), encoding="utf-8")
        command_script_path.chmod(0o700)
        log_path.touch()

        metadata = {
            "run_id": run_id,
            "status": "running",
            "created_at": utc_now(),
            "started_at": utc_now(),
            "finished_at": None,
            "exit_code": None,
            "host": platform.node(),
            "pid": None,
            "cwd": cwd,
            "command": command,
            "conda_prefix": conda_prefix,
            "conda_env_name": conda_env_name,
            "module_setup": module_setup,
            "env": env_vars,
            "timeout_seconds": timeout_seconds,
            "command_script": str(command_script_path),
            "log_path": str(log_path),
        }

        launch_command = self._build_launch_command(command_script_path, conda_prefix, conda_env_name)
        process_env = os.environ.copy()
        process_env["GPU_AGENT_RUN_ID"] = run_id
        process_env["GPU_AGENT_LOG_PATH"] = str(log_path)
        process_env["GPU_AGENT_CWD"] = cwd

        log_handle = log_path.open("a", encoding="utf-8", buffering=1)
        process = subprocess.Popen(
            launch_command,
            cwd=cwd,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=process_env,
            start_new_session=True,
        )
        log_handle.close()

        metadata["pid"] = process.pid
        write_json(metadata_path, metadata)

        with self.lock:
            self.active_runs[run_id] = ActiveRun(process=process, metadata_path=metadata_path, log_path=log_path)

        thread = threading.Thread(
            target=self._wait_for_process,
            args=(run_id, timeout_seconds),
            daemon=True,
        )
        thread.start()
        return metadata

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self.lock:
            active_run = self.active_runs.get(run_id)
            if active_run is None:
                raise KeyError(run_id)
            active_run.cancel_requested = True

        self._terminate_process_group(active_run.process.pid)
        metadata = read_json(active_run.metadata_path)
        metadata["status"] = "cancelling"
        write_json(active_run.metadata_path, metadata)
        return metadata

    def get_logs(self, run_id: str, offset: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)

        log_path = Path(run["log_path"])
        if not log_path.is_file():
            return {"run_id": run_id, "text": "", "offset": offset, "next_offset": offset, "complete": run["status"] in TERMINAL_STATES}

        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            text = handle.read()
            next_offset = handle.tell()

        return {
            "run_id": run_id,
            "text": text,
            "offset": offset,
            "next_offset": next_offset,
            "complete": run["status"] in TERMINAL_STATES,
        }

    def _build_command_script(self, env_vars: dict[str, str], module_setup: str, command: str) -> str:
        exports = []
        for key, value in sorted(env_vars.items()):
            exports.append(f"export {key}={shlex.quote(str(value))}")

        parts = [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'if [ -n "${MODULESHOME:-}" ] && [ -f "${MODULESHOME}/init/bash" ]; then',
            '    source "${MODULESHOME}/init/bash"',
            "elif [ -f /etc/profile.d/modules.sh ]; then",
            "    source /etc/profile.d/modules.sh",
            "fi",
            "",
        ]

        if exports:
            parts.extend(exports)
            parts.append("")

        if module_setup:
            parts.append(module_setup.rstrip())
            parts.append("")

        parts.append(command.rstrip())
        parts.append("")
        return "\n".join(parts)

    def _build_launch_command(
        self,
        command_script_path: Path,
        conda_prefix: str | None,
        conda_env_name: str | None,
    ) -> list[str]:
        if not conda_prefix and not conda_env_name:
            return ["/bin/bash", str(command_script_path)]

        selector = f"-p {shlex.quote(str(conda_prefix))}" if conda_prefix else f"-n {shlex.quote(str(conda_env_name))}"
        outer = (
            f"source {shlex.quote(str(self.conda_sh))} && "
            f"conda run --no-capture-output {selector} bash {shlex.quote(str(command_script_path))}"
        )
        return ["/bin/bash", "-lc", outer]

    def _wait_for_process(self, run_id: str, timeout_seconds: float | None) -> None:
        with self.lock:
            active_run = self.active_runs[run_id]
            process = active_run.process

        status = "failed"
        exit_code: int | None = None
        try:
            if timeout_seconds:
                exit_code = process.wait(timeout=timeout_seconds)
            else:
                exit_code = process.wait()
            if active_run.cancel_requested:
                status = "cancelled"
            else:
                status = "succeeded" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            active_run.cancel_requested = True
            self._terminate_process_group(process.pid)
            status = "timed_out"
        finally:
            metadata = read_json(active_run.metadata_path)
            metadata["status"] = status
            metadata["exit_code"] = exit_code if status != "timed_out" else 124
            metadata["finished_at"] = utc_now()
            write_json(active_run.metadata_path, metadata)
            with self.lock:
                self.active_runs.pop(run_id, None)

    def _terminate_process_group(self, pid: int) -> None:
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.killpg(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.2)

        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            return


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "CodexGpuBridge/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "host": platform.node(),
                    "time": utc_now(),
                },
            )
            return

        if not self._authorized():
            return

        if parsed.path == "/runs":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["50"])[0])
            self._send_json(HTTPStatus.OK, {"runs": self.server.run_manager.list_runs(limit=limit)})
            return

        parts = parsed.path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "runs":
            run = self.server.run_manager.get_run(parts[1])
            if run is None:
                self._send_error_json(HTTPStatus.NOT_FOUND, "run_not_found")
                return
            self._send_json(HTTPStatus.OK, run)
            return

        if len(parts) == 3 and parts[0] == "runs" and parts[2] == "logs":
            params = parse_qs(parsed.query)
            offset = int(params.get("offset", ["0"])[0])
            try:
                payload = self.server.run_manager.get_logs(parts[1], offset=offset)
            except KeyError:
                self._send_error_json(HTTPStatus.NOT_FOUND, "run_not_found")
                return
            self._send_json(HTTPStatus.OK, payload)
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, "unknown_route")

    def do_POST(self) -> None:
        if not self._authorized():
            return

        parsed = urlparse(self.path)
        if parsed.path == "/run":
            try:
                payload = self._read_json_body()
                result = self.server.run_manager.submit(payload)
            except ValueError as exc:
                self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._send_json(HTTPStatus.ACCEPTED, result)
            return

        parts = parsed.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "runs" and parts[2] == "cancel":
            try:
                result = self.server.run_manager.cancel(parts[1])
            except KeyError:
                self._send_error_json(HTTPStatus.NOT_FOUND, "run_not_found")
                return
            self._send_json(HTTPStatus.OK, result)
            return

        self._send_error_json(HTTPStatus.NOT_FOUND, "unknown_route")

    def log_message(self, format: str, *args: Any) -> None:
        message = "%s - - [%s] %s\n" % (
            self.client_address[0],
            self.log_date_time_string(),
            format % args,
        )
        print(message, end="")

    def _authorized(self) -> bool:
        token = self.server.auth_token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        if header == f"Bearer {token}":
            return True
        self._send_error_json(HTTPStatus.UNAUTHORIZED, "unauthorized")
        return False

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json(status, {"error": message})

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class GpuAgentServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], auth_token: str | None, run_manager: RunManager) -> None:
        super().__init__(server_address, RequestHandler)
        self.auth_token = auth_token
        self.run_manager = run_manager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute-node GPU command server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=9000, type=int)
    parser.add_argument("--state-dir", default=str(Path(__file__).resolve().parent.parent / "state"))
    parser.add_argument("--token-file")
    parser.add_argument("--conda-sh")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_dir = Path(args.state_dir).expanduser().resolve()
    token = None
    if args.token_file:
        token = Path(args.token_file).expanduser().read_text(encoding="utf-8").strip()

    run_manager = RunManager(state_dir=state_dir, conda_sh=detect_conda_sh(args.conda_sh))
    server = GpuAgentServer((args.host, args.port), auth_token=token, run_manager=run_manager)

    print(
        json.dumps(
            {
                "event": "server_started",
                "host": args.host,
                "port": args.port,
                "state_dir": str(state_dir),
                "conda_sh": run_manager.conda_sh,
                "time": utc_now(),
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
