from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from .common import BenchError


def image_id(image):
    try:
        return subprocess.check_output(
            ["docker", "image", "inspect", "--format", "{{.Id}}", image],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        raise BenchError(f"Build or pull the configured sandbox image first: {image}") from None


def execute(workspace: Path, code: str, settings: dict, timeout: int = 60):
    """The only model-code executor. No host-shell fallback; no inherited secrets."""
    timeout = max(1, min(int(timeout), int(settings.get("max_seconds", 120))))
    if len(code.encode()) > 1_000_000:
        raise BenchError("Code exceeds 1 MB")
    image = settings.get("image", "gaos-bench-sandbox:latest")
    name = "gaos-bench-" + uuid.uuid4().hex
    args = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        settings.get("memory", "4g"),
        "--cpus",
        str(settings.get("cpus", 2)),
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,size=512m",
        "--mount",
        f"type=bind,source={workspace.resolve()},target=/workspace",
        "--workdir",
        "/workspace",
        "--env",
        "HOME=/tmp",
        "--env",
        "MPLCONFIGDIR=/tmp/matplotlib",
        image,
        "python",
        "-",
    ]
    # Files bound stdout/stderr memory even when submitted code prints very large output.
    import tempfile

    with tempfile.TemporaryFile() as output:
        try:
            proc = subprocess.run(
                args,
                input=code.encode(),
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            status = "completed" if proc.returncode == 0 else "execution_error"
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            status, returncode = "timeout", None
        except FileNotFoundError:
            raise BenchError("Docker is required for model-generated code execution") from None
        finally:
            try:
                subprocess.run(
                    ["docker", "rm", "-f", name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        size = output.tell()
        output.seek(max(0, size - 24000))
        log = output.read(24000).decode("utf-8", errors="replace")
    return {"status": status, "exit_code": returncode, "output": log, "truncated": size > 24000}
