from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class BenchError(ValueError):
    pass


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".json-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def safe_path(root: Path, relative: str) -> Path:
    """Agent-controlled names cannot address another run or follow symlinks."""
    part = Path(relative)
    if part.is_absolute() or ".." in part.parts or not part.parts:
        raise BenchError("Expected a relative path inside the task workspace")
    root = root.resolve()
    current = root
    for piece in part.parts:
        current = current / piece
        if current.is_symlink():
            raise BenchError("Symlinks are not accepted in task paths")
    result = current.resolve()
    if not result.is_relative_to(root):
        raise BenchError("Path escapes the task workspace")
    return result


def safe_copy(source: Path, target: Path):
    if source.is_symlink():
        raise BenchError(f"Symlink in input or submission: {source.name}")
    if source.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            safe_copy(child, target / child.name)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    else:
        raise BenchError(f"Missing file or unsupported file type: {source.name}")


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def revision(path):
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except (subprocess.SubprocessError, OSError):
        return None


@dataclass
class Task:
    benchmark: str
    task_id: str
    variant: str
    prompt: str
    evaluator: str
    artifacts: list[str]
    inputs: list[tuple[Path, str]] = field(default_factory=list)
    private: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def public(self, detail=True):
        result = {
            "benchmark": self.benchmark,
            "task_id": self.task_id,
            "variant": self.variant,
            "tags": self.tags,
            "artifacts": self.artifacts,
        }
        if detail:
            result["prompt"] = self.prompt
            result["input_paths"] = [dest for _, dest in self.inputs]
        return result


class Config:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if self.data.get("schema_version") != 1:
            raise BenchError("benchmarks.yaml must have schema_version: 1")
        self.base = self.path.parent
        self.runs = self.resolve(self.data.get("runs_dir", "runs"))
        self.benchmarks = self.data.get("benchmarks", {})

    def resolve(self, path):
        p = Path(os.path.expandvars(str(path))).expanduser()
        if "$" in str(p):
            raise BenchError(f"Unresolved environment variable in path: {path}")
        return p.resolve() if p.is_absolute() else (self.base / p).resolve()

    def spec(self, name):
        if name not in self.benchmarks:
            raise BenchError(f"Benchmark is not configured: {name}")
        return self.benchmarks[name]


def validate_id(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", str(value)):
        raise BenchError("Task IDs must contain only letters, numbers, underscores, dots and hyphens")
    return str(value)
