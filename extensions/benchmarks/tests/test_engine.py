import json
import sys
import time

import pytest
import yaml
from gaos_bench.common import BenchError, read_json, safe_copy, safe_path
from gaos_bench.engine import Engine
from gaos_bench.evaluators import validate_result


@pytest.fixture
def configured(tmp_path):
    public = tmp_path / "public.csv"
    public.write_text("x\n1\n2\n")
    # This small evaluator exercises the documented external-evaluator contract.
    script = tmp_path / "grade.py"
    script.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "c=json.loads(Path(sys.argv[1]).read_text())\n"
        "v=(Path(c['submission'])/'answer.txt').read_text().strip()\n"
        "result={'status':'completed','metrics':{'accuracy':float(v == '3')},'feedback':['evaluated']}\n"
        "Path(c['output']).write_text(json.dumps(result))\n"
    )
    index = tmp_path / "tasks.jsonl"
    row = {
        "task_id": "sum",
        "prompt": "Sum the supplied values.",
        "evaluator": "local-test",
        "artifacts": ["answer.txt"],
        "private": {"answer": "NEVER-SHOW-THIS"},
        "inputs": [{"source": "public.csv", "destination": "input.csv"}],
    }
    index.write_text(json.dumps(row) + "\n")
    config = tmp_path / "benchmarks.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "runs_dir": "runs",
                "benchmarks": {
                    "test": {
                        "adapter": "manifest",
                        "manifest": "tasks.jsonl",
                        "evaluators": {"local-test": {"command": [sys.executable, str(script), "{context}"]}},
                    }
                },
            }
        )
    )
    return Engine(config)


def test_end_to_end_freeze_and_repeated_submission(configured):
    e = configured
    public = e.get_task("test", "sum")
    assert "NEVER-SHOW-THIS" not in json.dumps(public)
    started = e.start("test", "sum")
    rid = started["run_id"]
    assert "NEVER-SHOW-THIS" not in json.dumps(started)
    assert e.read_file(rid, "input.csv")["text"] == "x\n1\n2\n"
    e.write_file(rid, "answer.txt", "3")
    e.submit(rid, background=False)
    with pytest.raises(BenchError, match="frozen"):
        e.write_file(rid, "answer.txt", "9")
    result = e.grade(rid)
    assert result["status"] == "completed"
    assert result["metrics"] == {"accuracy": 1.0}
    assert e.submit(rid) == result
    assert e.grade(rid) == result
    assert "NEVER-SHOW-THIS" not in json.dumps(e.status(rid))
    assert (e.folder(rid) / "feedback.md").is_file()


def test_background_evaluation(configured):
    rid = configured.start("test", "sum")["run_id"]
    configured.write_file(rid, "answer.txt", "wrong")
    configured.submit(rid)
    for _ in range(100):
        state = configured.status(rid)
        if state["status"] not in {"submitted", "evaluating"}:
            break
        time.sleep(0.05)
    assert state["status"] == "completed"
    assert state["metrics"]["accuracy"] == 0


def test_missing_artifact_keeps_run_open(configured):
    rid = configured.start("test", "sum")["run_id"]
    assert configured.submit(rid)["status"] == "invalid_submission"
    assert configured.status(rid)["status"] == "running"
    configured.write_file(rid, "answer.txt", "3")


@pytest.mark.parametrize("path", ["../state.json", "/etc/passwd", "a/../../state.json"])
def test_path_escape_is_rejected(configured, path):
    rid = configured.start("test", "sum")["run_id"]
    with pytest.raises(BenchError):
        configured.read_file(rid, path)
    with pytest.raises(BenchError):
        configured.write_file(rid, path, "x")


def test_symlink_does_not_expose_private_files(configured):
    rid = configured.start("test", "sum")["run_id"]
    folder = configured.folder(rid)
    (folder / "workspace/answer.txt").symlink_to(folder / "state.json")
    with pytest.raises(BenchError):
        configured.read_file(rid, "answer.txt")
    with pytest.raises(BenchError):
        configured.submit(rid, background=False)


def test_config_change_cannot_silently_change_evaluator(configured):
    rid = configured.start("test", "sum")["run_id"]
    configured.write_file(rid, "answer.txt", "3")
    configured.submit(rid, background=False)
    config = configured.config.path
    config.write_text(config.read_text() + "\n# changed\n")
    assert configured.grade(rid)["status"] == "blocked"


@pytest.mark.parametrize(
    "result",
    [
        {"status": "completed", "metrics": {}},
        {"status": "completed", "metrics": {"score": float("nan")}},
        {"status": "completed", "metrics": {"score": True}},
        {"status": "evaluator_error", "metrics": {"score": 0}},
        {"status": "made-up", "metrics": {}},
    ],
)
def test_bad_scores_fail_closed(result):
    with pytest.raises(BenchError):
        validate_result(result)


def test_evaluator_failure_is_not_zero(configured):
    (configured.config.base / "grade.py").write_text("raise RuntimeError('test failure')")
    rid = configured.start("test", "sum")["run_id"]
    configured.write_file(rid, "answer.txt", "3")
    configured.submit(rid, background=False)
    result = configured.grade(rid)
    assert result["status"] == "evaluator_error"
    assert result["metrics"] == {}


def test_missing_data_blocks_without_fake_tasks(configured):
    (configured.config.base / "public.csv").unlink()
    assert configured.start("test", "sum")["status"] == "blocked"


def test_no_cross_run_reads(configured):
    a = configured.start("test", "sum")["run_id"]
    b = configured.start("test", "sum")["run_id"]
    configured.write_file(a, "answer.txt", "private attempt")
    with pytest.raises(BenchError):
        configured.read_file(b, f"../../{a}/workspace/answer.txt")


def test_sandbox_not_silently_replaced_by_host(configured, monkeypatch):
    from gaos_bench import sandbox

    def missing(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(sandbox.subprocess, "run", missing)
    monkeypatch.setattr(sandbox, "image_id", lambda _: "sha256:test")
    rid = configured.start("test", "sum")["run_id"]
    with pytest.raises(BenchError, match="Docker"):
        configured.execute(rid, "print(1)")
    assert configured.status(rid)["code_calls"] == 1


def test_copy_rejects_links_in_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "escape").symlink_to("/etc/passwd")
    with pytest.raises(BenchError):
        safe_copy(source, tmp_path / "target")
    with pytest.raises(BenchError):
        safe_path(tmp_path, "../outside")


def test_public_manifest_records_input_and_submission_hashes(configured):
    rid = configured.start("test", "sum")["run_id"]
    configured.write_file(rid, "answer.txt", "3")
    configured.submit(rid, background=False)
    state = read_json(configured.folder(rid) / "state.json")
    assert len(state["input_sha256"]["input.csv"]) == 64
    assert len(state["submission_sha256"]["answer.txt"]) == 64
