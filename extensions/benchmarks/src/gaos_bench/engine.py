from __future__ import annotations

import contextlib
import fcntl
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from . import sandbox
from .adapters import SOURCES, select, tasks
from .common import BenchError, Config, file_hash, read_json, revision, safe_copy, safe_path, write_json
from .evaluators import evaluate, preflight


class Engine:
    def __init__(self, config_path):
        self.config = Config(config_path)

    def catalog(self):
        result = []
        for name in self.config.benchmarks:
            entry = {"benchmark": name, "source": SOURCES.get(name)}
            try:
                items = tasks(self.config, name)
                entry.update(task_variants=len(items), status="indexed" if items else "no_tasks")
            except (OSError, ValueError, KeyError) as exc:
                entry.update(status="not_configured", message=type(exc).__name__)
            result.append(entry)
        return result

    def list_tasks(self, benchmark, query="", variant=None, offset=0, limit=20):
        if offset < 0 or not 1 <= limit <= 100:
            raise BenchError("Use offset >= 0 and limit between 1 and 100")
        entries = [
            t
            for t in tasks(self.config, benchmark)
            if (variant is None or t.variant == variant)
            and query.lower() in (t.task_id + " " + " ".join(t.tags)).lower()
        ]
        return {
            "total": len(entries),
            "offset": offset,
            "tasks": [t.public(False) for t in entries[offset : offset + limit]],
        }

    def get_task(self, benchmark, task_id, variant=None):
        task = select(self.config, benchmark, task_id, variant)
        return {**task.public(), "readiness_issues": preflight(self.config, task)}

    def folder(self, run_id):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            raise BenchError("Invalid run ID")
        folder = self.config.runs / run_id
        if not (folder / "state.json").exists():
            raise BenchError("Unknown run ID")
        return folder

    @contextlib.contextmanager
    def locked(self, run_id):
        folder = self.folder(run_id)
        with (folder / "lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield folder, read_json(folder / "state.json")

    def start(self, benchmark, task_id, variant=None):
        task = select(self.config, benchmark, task_id, variant)
        issues = preflight(self.config, task)
        if issues:
            return {"status": "blocked", "readiness_issues": issues, **task.public(False)}
        run_id = uuid.uuid4().hex
        folder = self.config.runs / run_id
        folder.mkdir(parents=True, mode=0o700)
        workspace = folder / "workspace"
        workspace.mkdir()
        input_hashes = {}
        for source, destination in task.inputs:
            target = safe_path(workspace, destination)
            safe_copy(source, target)
            for path in [target] if target.is_file() else sorted(target.rglob("*")):
                if path.is_file():
                    input_hashes[str(path.relative_to(workspace))] = file_hash(path)
        state = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "running",
            "created_at": time.time(),
            "task": task.public(),
            "evaluator": task.evaluator,
            "private": task.private,
            "source_revision": revision(task.private["root"]) if task.private.get("root") else None,
            "input_sha256": input_hashes,
            "code_calls": 0,
            "config_sha256": file_hash(self.config.path),
            "sandbox": self.config.data.get("sandbox", {}),
        }
        if (
            task.evaluator == "dare"
            and task.variant == "v1"
            and task.private["kind"] != "time_series_analysis"
        ):
            state["sandbox_image_id"] = read_json(task.private["reference_receipt"])["image_id"]
            state["sandbox"] = {**state["sandbox"], "image": state["sandbox_image_id"]}
        (workspace / "TASK.md").write_text(task.prompt, encoding="utf-8")
        write_json(folder / "state.json", state)
        return {
            "run_id": run_id,
            "status": "running",
            "task": task.public(),
            "working_directory": "/workspace",
            "submission_note": "Write the required artifacts into /workspace, then submit_run once.",
        }

    def _running(self, state):
        if state["status"] != "running":
            raise BenchError("This run is frozen; start a new run for another attempt")

    def write_file(self, run_id, path, content):
        with self.locked(run_id) as (folder, state):
            self._running(state)
            if len(content.encode()) > 1_000_000:
                raise BenchError("write_file is limited to 1 MB; create larger artifacts with sandbox Python")
            target = safe_path(folder / "workspace", path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return {"path": path, "bytes": len(content.encode())}

    def read_file(self, run_id, path, offset=0, limit=16000):
        if offset < 0 or not 1 <= limit <= 64000:
            raise BenchError("Invalid read offset or limit")
        with self.locked(run_id) as (folder, state):
            workspace = folder / "workspace"
            target = workspace if path == "." else safe_path(workspace, path)
            if target.is_dir():
                entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
                return {"entries": entries[:200], "truncated": len(entries) > 200}
            with target.open("rb") as f:
                if b"\x00" in f.read(8192):
                    raise BenchError(
                        "This is a binary file; read_file only supports text. "
                        "Use execute_python with sqlite3, pandas or the appropriate reader "
                        "to inspect its schema and rows."
                    )
                f.seek(offset)
                data = f.read(limit + 1)
            return {"text": data[:limit].decode("utf-8", errors="replace"), "truncated": len(data) > limit}

    def execute(self, run_id, code, timeout=60):
        with self.locked(run_id) as (folder, state):
            self._running(state)
            if state["code_calls"] >= self.config.data.get("max_code_calls", 80):
                raise BenchError("Code execution budget exhausted; submit existing artifacts")
            state["code_calls"] += 1
            if not state.get("sandbox_image_id"):
                state["sandbox_image_id"] = sandbox.image_id(
                    state["sandbox"].get("image", "gaos-bench-sandbox:latest")
                )
                state["sandbox"] = {**state["sandbox"], "image": state["sandbox_image_id"]}
            write_json(folder / "state.json", state)
            log_dir = folder / "execution"
            log_dir.mkdir(exist_ok=True)
            (log_dir / f"{state['code_calls']:04}.py").write_text(code)
            result = sandbox.execute(folder / "workspace", code, state["sandbox"], timeout)
            write_json(log_dir / f"{state['code_calls']:04}.json", result)
            return result

    def submit(self, run_id, background=True):
        with self.locked(run_id) as (folder, state):
            if state["status"] != "running":
                return self._status(state)
            workspace = folder / "workspace"
            missing = [p for p in state["task"]["artifacts"] if not safe_path(workspace, p).exists()]
            if missing:
                return {
                    "status": "invalid_submission",
                    "missing_artifacts": missing,
                    "run_id": run_id,
                    "feedback": ["Run remains open so you can supply the missing artifacts."],
                }
            if state["evaluator"] == "dacomp-de":
                if not state.get("sandbox_image_id"):
                    state["sandbox_image_id"] = sandbox.image_id(
                        state["sandbox"].get("image", "gaos-bench-sandbox:latest")
                    )
                    state["sandbox"] = {**state["sandbox"], "image": state["sandbox_image_id"]}
                result = sandbox.execute(
                    workspace,
                    "import os, runpy\nos.chdir('project')\nrunpy.run_path('run.py', run_name='__main__')\n",
                    state["sandbox"],
                    timeout=120,
                )
                write_json(folder / "pipeline-execution.json", result)
                if result["status"] != "completed":
                    return {
                        "status": "invalid_submission",
                        "run_id": run_id,
                        "feedback": ["project/run.py failed inside the sandbox"],
                        "execution": result,
                    }
            submission = folder / "submission"
            with tempfile.TemporaryDirectory(dir=folder, prefix=".freeze-") as temp:
                staged = Path(temp) / "artifacts"
                staged.mkdir()
                for name in state["task"]["artifacts"]:
                    safe_copy(safe_path(workspace, name), safe_path(staged, name))
                if state["evaluator"] == "dacomp-da":
                    # Preserve report visual evidence without copying raw input databases.
                    for source in workspace.rglob("*"):
                        if (
                            source.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp"}
                            and source.is_file()
                        ):
                            safe_copy(source, safe_path(staged, str(source.relative_to(workspace))))
                staged.rename(submission)
            state["submission_sha256"] = {
                str(p.relative_to(submission)): file_hash(p) for p in submission.rglob("*") if p.is_file()
            }
            state.update(status="submitted", submitted_at=time.time())
            write_json(folder / "state.json", state)
            if background:
                with (folder / "job.log").open("ab") as log:
                    process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "gaos_bench",
                            "--config",
                            str(self.config.path),
                            "evaluate",
                            run_id,
                        ],
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                state["worker_pid"] = process.pid
                write_json(folder / "state.json", state)
            return self._status(state)

    def grade(self, run_id):
        with self.locked(run_id) as (folder, state):
            if state["status"] not in {"submitted"}:
                return self._status(state)
            if state["config_sha256"] != file_hash(self.config.path):
                state.update(
                    status="blocked",
                    result={
                        "status": "blocked",
                        "metrics": {},
                        "feedback": [
                            "Configuration changed after this run started; restore it or start a new run"
                        ],
                    },
                )
                write_json(folder / "state.json", state)
                return self._status(state)
            state.update(status="evaluating", worker_pid=os.getpid(), evaluation_started_at=time.time())
            write_json(folder / "state.json", state)
        try:
            result = evaluate(self.config, state, folder)
        except Exception as exc:
            # Full diagnostics are operator-only; upstream exception strings can include gold data.
            import traceback

            (folder / "evaluator-error.txt").write_text(traceback.format_exc())
            result = {
                "status": "evaluator_error",
                "metrics": {},
                "feedback": [f"Evaluator failed ({type(exc).__name__}); inspect the operator logs"],
            }
        with self.locked(run_id) as (folder, state):
            state.update(status=result["status"], result=result, finished_at=time.time())
            write_json(folder / "state.json", state)
            write_json(folder / "feedback.json", self._status(state))
            lines = [
                f"# {state['task']['benchmark']} / {state['task']['task_id']}",
                f"Status: {state['status']}",
                f"Variant: {state['task']['variant']}",
                "",
            ]
            lines += [f"- {k}: {v}" for k, v in result.get("metrics", {}).items()]
            lines += ["", *result.get("feedback", [])]
            (folder / "feedback.md").write_text("\n".join(lines) + "\n")
            return self._status(state)

    def _status(self, state):
        result = {
            "run_id": state["run_id"],
            "status": state["status"],
            "benchmark": state["task"]["benchmark"],
            "task_id": state["task"]["task_id"],
            "variant": state["task"]["variant"],
            "code_calls": state["code_calls"],
        }
        if "result" in state:
            # No raw result, gold, hidden paths or evaluator process environment reaches the model.
            result.update(
                metrics=state["result"].get("metrics", {}), feedback=state["result"].get("feedback", [])
            )
        return result

    def status(self, run_id):
        with self.locked(run_id) as (folder, state):
            if state["status"] in {"submitted", "evaluating"} and state.get("worker_pid"):
                try:
                    os.kill(state["worker_pid"], 0)
                except ProcessLookupError:
                    state.update(
                        status="evaluator_error",
                        result={
                            "metrics": {},
                            "feedback": ["Evaluator worker stopped before producing a result"],
                        },
                    )
                    write_json(folder / "state.json", state)
            return self._status(state)

    def prepare_reference(self, task_id):
        """Operator CLI only. Generate IF gold with the same image as the solver."""
        import importlib.util

        task = select(self.config, "dare-bench", task_id, "v1")
        if task.private["kind"] == "time_series_analysis":
            raise BenchError("Time series uses the released ground truth and needs no IF reference")
        root = Path(task.private["root"])
        settings = self.config.data.get("sandbox", {})
        image = settings.get("image", "gaos-bench-sandbox:latest")
        actual_image = sandbox.image_id(image)
        spec = importlib.util.spec_from_file_location(
            "dare_reference", root / "scripts/reference_solution.py"
        )
        upstream = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(upstream)
        code = upstream.generate_reference_solution_code(task.private["metadata"])
        with tempfile.TemporaryDirectory(prefix="gaos-reference-") as temp:
            workspace = Path(temp)
            source = root / "data/eval/databases" / task_id / "source"
            for file in source.iterdir():
                if file.name.startswith(("train_v1_no_err.", "val_v1.")):
                    safe_copy(file, workspace / file.name)
            result = sandbox.execute(workspace, code, {**settings, "image": actual_image}, timeout=120)
            prediction = workspace / "simulated_pred_local.csv"
            if result["status"] != "completed" or not prediction.exists():
                raise BenchError("Reference generation failed: " + result["output"])
            safe_copy(prediction, Path(task.private["gold"]))
        write_json(
            task.private["reference_receipt"],
            {
                "image": image,
                "image_id": actual_image,
                "sha256": file_hash(task.private["gold"]),
                "created_at": time.time(),
            },
        )
        return {"status": "ready", "task_id": task_id, "image_id": actual_image}
