"""Optional contract tests against real, independently cloned upstream releases."""

import json
import os
from pathlib import Path

import pytest
import yaml
from gaos_bench.adapters import tasks
from gaos_bench.engine import Engine


def upstream(name):
    value = os.getenv(f"GAOS_TEST_{name.upper()}_ROOT")
    if not value:
        pytest.skip(f"Set GAOS_TEST_{name.upper()}_ROOT for the official source contract test")
    return Path(value)


def engine(tmp_path, name, spec):
    path = tmp_path / "benchmarks.yaml"
    path.write_text(yaml.safe_dump({"schema_version": 1, "runs_dir": "runs", "benchmarks": {name: spec}}))
    return Engine(path)


def test_real_dare_baseline_and_official_evaluator(tmp_path):
    import sqlite3

    import pandas as pd
    from sklearn.dummy import DummyClassifier

    root = upstream("dare")
    e = engine(tmp_path, "dare-bench", {"root": str(root)})
    entries = tasks(e.config, "dare-bench")
    assert len(entries) == 324
    chosen = next(t for t in entries if t.variant == "v2" and "pokemonunitedataset" in t.task_id)
    rid = e.start("dare-bench", chosen.task_id, "v2")["run_id"]
    workspace = e.folder(rid) / "workspace"
    assert not (workspace / "verify").exists()
    assert not (workspace / "all_metadata.json").exists()

    def load(path):
        with sqlite3.connect(path) as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            frames = [pd.read_sql_query('SELECT * FROM "' + n.replace('"', '""') + '"', db) for n in names]
        data = frames[0]
        for frame in frames[1:]:
            data = data.merge(frame, on="row_id")
        return data

    train = load(workspace / "train_v2.sqlite")
    val = load(workspace / "val_v2.sqlite")
    # Training-only baseline; the hidden answer is never used to produce predictions.
    model = DummyClassifier(strategy="most_frequent").fit([[0]] * len(train), train["Role"])
    pred = pd.DataFrame({"row_id": val["row_id"], "Role": model.predict([[0]] * len(val))})
    pred.to_csv(workspace / "prediction.csv", index=False)
    e.submit(rid, background=False)
    result = e.grade(rid)
    assert result["status"] == "completed", result
    assert 0 <= result["metrics"]["final_score"] <= 1


def test_real_dare_if_requires_environment_reference(tmp_path):
    e = engine(tmp_path, "dare-bench", {"root": str(upstream("dare"))})
    task = next(t for t in tasks(e.config, "dare-bench") if t.variant == "v1" and "classification" in t.tags)
    result = e.start("dare-bench", task.task_id, "v1")
    assert result["status"] == "blocked"
    assert any("prepare-reference" in x for x in result["readiness_issues"])


def test_real_coda_evaluator_does_not_score_missing_unselected_tasks(tmp_path):
    root = upstream("coda")
    community = tmp_path / "communities/community_26/full_community"
    community.mkdir(parents=True)
    # Only a format/evaluator test; no claim of solving a real CoDA task.
    (community / "fixture.txt").write_text("contract-test input")
    e = engine(tmp_path, "coda-bench", {"root": str(root), "communities": str(tmp_path / "communities")})
    assert e.list_tasks("coda-bench")["total"] == 1009
    assert "reference_code" not in json.dumps(e.get_task("coda-bench", "0"))
    rid = e.start("coda-bench", "0")["run_id"]
    e.write_file(rid, "answer.txt", "38%")
    e.submit(rid, background=False)
    result = e.grade(rid)
    assert result["status"] == "completed", result
    assert result["metrics"] == {"exact_accuracy": 1, "numeric_accuracy": 1}


def test_real_ddr_indexes_entities_not_hidden_questions(tmp_path):
    e = engine(tmp_path, "ddr-bench", {"root": str(upstream("ddr"))})
    assert e.list_tasks("ddr-bench")["total"] == 291
    task = e.get_task("ddr-bench", "10k-6201")
    assert "qa_pairs" not in json.dumps(task)
    assert task["readiness_issues"]


def test_real_ambig_pairs_hide_oracle_and_full_prompt(tmp_path):
    e = engine(tmp_path, "ambig-ds", {"root": str(upstream("ambig"))})
    assert len([t for t in tasks(e.config, "ambig-ds") if "target" in t.tags]) == 102
    task = e.get_task("ambig-ds", "titanic", "ambiguous")
    text = json.dumps(task)
    assert "true_target_column_in_ambig" not in text
    assert "Survived" not in text
    assert "cv_decoy" not in text


def test_real_ambig_evaluator_restores_headers_and_excludes_private_files(tmp_path):
    root = upstream("ambig")
    prepared = tmp_path / "prepared/titanic/ambiguous"
    prepared.mkdir(parents=True)
    (prepared / "train.csv").write_text("id,f_01,val_1,val_2\n1,1,0,1\n")
    (prepared / "test.csv").write_text("id,f_01\n2,1\n3,2\n")
    (prepared / "_manifest.json").write_text('{"secret":"ORACLE"}')
    gold = tmp_path / "gold/titanic"
    gold.mkdir(parents=True)
    (gold / "test_answer.csv").write_text("PassengerId,Survived\n2,0\n3,1\n")
    e = engine(
        tmp_path,
        "ambig-ds",
        {"root": str(root), "prepared": str(tmp_path / "prepared"), "gold": str(tmp_path / "gold")},
    )
    rid = e.start("ambig-ds", "titanic", "ambiguous")["run_id"]
    assert not (e.folder(rid) / "workspace/data/_manifest.json").exists()
    e.write_file(rid, "submission.csv", "id,prediction\n3,1\n2,0\n")
    e.submit(rid, background=False)
    result = e.grade(rid)
    assert result["status"] == "completed", result
    assert result["metrics"]["competition_metric"] == 1


def test_real_dacomp_da_and_arch_index(tmp_path):
    root = upstream("dacomp")
    da_index = os.getenv("GAOS_TEST_DACOMP_DA_INDEX")
    if not da_index:
        pytest.skip("Set GAOS_TEST_DACOMP_DA_INDEX")
    e = engine(
        tmp_path,
        "dacomp",
        {"root": str(root), "da_data": str(Path(da_index).parent), "da_index": Path(da_index).name},
    )
    items = tasks(e.config, "dacomp")
    assert sum(t.variant == "da" for t in items) == 100
    assert any(t.variant == "de-arch" for t in items)
    assert all("rubric" not in t.public() and "private" not in t.public() for t in items)


def test_real_ambig_objective_indexes_both_conditions_without_metric_manifest(tmp_path):
    objective = upstream("objective")
    e = engine(tmp_path, "ambig-ds", {"root": str(upstream("ambig")), "objective_root": str(objective)})
    all_tasks = tasks(e.config, "ambig-ds")
    assert len(all_tasks) == 224
    chosen = e.get_task("ambig-ds", "spooky-author-identification", "objective-ambiguous")
    original = (objective / "prompts/spooky-author-identification/ambig_metric.md").read_text()
    assert chosen["prompt"] == original
    assert "metric_manifest" not in chosen
    assert "private" not in chosen
