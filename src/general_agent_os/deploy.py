"""Small local process deployment manager. Docker is available for restart policies."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

from .profile import Profile, ProfileError


def state_dir(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
        raise ProfileError("Deployment name must use letters, numbers, dots, underscores or hyphens")
    root = Path(os.getenv("GAOS_STATE_DIR", str(Path.home() / ".local/state/general-agent-os")))
    path = root / name
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def process_for(record: dict):
    try:
        proc = psutil.Process(record["pid"])
        if abs(proc.create_time() - record["created"]) < 0.01 and proc.status() != psutil.STATUS_ZOMBIE:
            return proc
    except (psutil.NoSuchProcess, KeyError):
        pass
    return None


def status(name: str) -> dict:
    path = state_dir(name) / "state.json"
    if not path.exists():
        return {"name": name, "running": False}
    record = json.loads(path.read_text())
    return {**record, "running": process_for(record) is not None}


def stop(name: str) -> dict:
    record = status(name)
    proc = process_for(record) if record["running"] else None
    if proc:
        children = proc.children(recursive=True)
        proc.terminate()
        _, alive = psutil.wait_procs([proc], timeout=10)
        if alive:
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs([proc] + children, timeout=3)
            for child in alive:
                child.kill()
        record["running"] = False
    return record


def deploy(profile: Profile, name: str, env_file: str | None = None) -> dict:
    directory = state_dir(name)
    if status(name)["running"]:
        raise ProfileError(f"Deployment {name} is already running; use gaos stop {name} first")
    settings = profile.data["os"]
    host, port = settings.get("host", "127.0.0.1"), settings["port"]
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError:
            raise ProfileError(f"Cannot bind {host}:{port}; choose a free port") from None
    command = [sys.executable, "-m", "general_agent_os", "serve"]
    for path in profile.files:
        command.extend(["--profile", str(path)])
    if env_file:
        command.extend(["--env-file", str(Path(env_file).resolve())])
    log_path = directory / "server.log"
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "ab") as log:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=profile.root,
        )
    record = {
        "name": name,
        "pid": proc.pid,
        "created": psutil.Process(proc.pid).create_time(),
        "port": port,
        "host": host,
        "log": str(log_path),
        "profiles": [str(p) for p in profile.files],
    }
    (directory / "state.json").write_text(json.dumps(record, indent=2))
    local_host = (
        "127.0.0.1" if host in {"0.0.0.0", "localhost"} else ("[::1]" if host in {"::", "::1"} else host)
    )
    try:
        with httpx.Client(trust_env=False, timeout=1) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise ProfileError(f"Server exited during startup. Inspect {log_path}")
                try:
                    response = client.get(f"http://{local_host}:{port}/health")
                    if response.status_code == 200:
                        return {**record, "running": True, "url": f"http://{local_host}:{port}"}
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
        raise ProfileError(f"Startup health check timed out. Inspect {log_path}")
    except BaseException:
        stop(name)
        raise
