"""Trusted evaluator dispatcher. Commands are operator configuration, never agent arguments."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import sys
from pathlib import Path

from . import sandbox
from .common import BenchError, file_hash, read_json, write_json

NATIVE = {"dare", "coda", "ddr", "ambig-target", "ambig-objective", "dacomp-da", "dacomp-de", "dacomp-arch"}
JUDGES = {"ddr", "dacomp-da", "dacomp-arch"}


def preflight(config, task):
    issues = []
    spec = config.spec(task.benchmark)
    for source, destination in task.inputs:
        if not source.exists():
            issues.append(f"Missing input {destination}; install this task's data")
    for key in ("gold", "metadata", "script", "qa"):
        if key in task.private and not Path(task.private[key]).exists():
            issues.append(f"Missing evaluator asset: {key}")
    route = spec.get("evaluators", {}).get(task.evaluator, {})
    if task.evaluator not in NATIVE and not route.get("command"):
        issues.append(f"Configure evaluator route: {task.evaluator}")
    if task.evaluator in JUDGES and not route.get("model"):
        issues.append(f"Configure judge model for {task.evaluator}")
    for env_name in route.get("required_env", []):
        if not os.getenv(env_name):
            issues.append(f"Missing evaluator environment variable: {env_name}")
    if task.evaluator == "dare" and task.variant == "v1" and task.private["kind"] != "time_series_analysis":
        receipt = Path(task.private["reference_receipt"])
        if not receipt.exists():
            issues.append("Run prepare-reference for this IF task in the configured sandbox image")
        else:
            expected = read_json(receipt)
            gold = Path(task.private["gold"])
            if not gold.exists() or expected.get("sha256") != file_hash(gold):
                issues.append("IF reference receipt does not match the current ground truth")
            if expected.get("image") != config.data.get("sandbox", {}).get(
                "image", "gaos-bench-sandbox:latest"
            ):
                issues.append("IF reference was generated using a different sandbox image")
            try:
                if expected.get("image_id") != sandbox.image_id(expected["image"]):
                    issues.append("Sandbox image changed; regenerate this IF reference")
            except (BenchError, KeyError) as exc:
                issues.append(str(exc))
    if task.evaluator == "dacomp-de":
        root = Path(task.private["root"])
        gold = config.resolve(route.get("gold_dir", str(root / "dacomp-de/evaluation_suite/gold")))
        if not gold.exists():
            issues.append("Download DAComp-DE gold databases")
    return issues


def validate_result(result):
    if not isinstance(result, dict) or result.get("status") not in {
        "completed",
        "invalid_submission",
        "evaluator_error",
        "blocked",
    }:
        raise BenchError("Evaluator returned an invalid status")
    metrics = result.get("metrics", {})
    if not isinstance(metrics, dict):
        raise BenchError("Evaluator metrics must be an object")
    for value in metrics.values():
        if not isinstance(value, (float, int)) or isinstance(value, bool) or not math.isfinite(value):
            raise BenchError("Evaluator returned a non-finite or non-numeric metric")
    if result["status"] == "completed" and not metrics:
        raise BenchError("Evaluator produced no valid metrics")
    if result["status"] != "completed" and metrics:
        raise BenchError("An unsuccessful evaluator must not return scored metrics")
    return result


def evaluate(config, state, folder):
    task = state["task"]
    spec = config.spec(task["benchmark"])
    route = spec.get("evaluators", {}).get(state["evaluator"], {})
    result_file = folder / "evaluation/result.json"
    result_file.parent.mkdir(exist_ok=True)
    context = {
        "task": task,
        "evaluator": state["evaluator"],
        "private": state["private"],
        "route": route,
        "submission": str(folder / "submission"),
        "output": str(result_file),
    }
    # Resolve operator path settings before passing them to an isolated evaluator process.
    for key in ("gold_dir", "config", "metadata_root"):
        if key in route:
            context["route"] = {**context["route"], key: str(config.resolve(route[key]))}
    context_file = folder / "evaluation/context.json"
    write_json(context_file, context)
    if route.get("command"):
        substitutions = {
            "context": str(context_file),
            "result": str(result_file),
            "submission": str(folder / "submission"),
            "task_id": task["task_id"],
        }
        command = [arg.format_map(substitutions) for arg in route["command"]]
    else:
        worker = Path(__file__).with_name("worker.py")
        command = [route.get("python", sys.executable), str(worker), str(context_file)]
    cwd = config.resolve(route["cwd"]) if route.get("cwd") else folder / "evaluation"
    timeout = int(route.get("timeout_seconds", 900))
    with (folder / "evaluation/evaluator.log").open("wb") as log:
        proc = subprocess.Popen(
            command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            return {"status": "evaluator_error", "metrics": {}, "feedback": ["Evaluator timed out"]}
    if proc.returncode != 0 or not result_file.exists():
        return {
            "status": "evaluator_error",
            "metrics": {},
            "feedback": ["Official evaluator failed; inspect the operator's evaluation/evaluator.log"],
        }
    return validate_result(read_json(result_file))
