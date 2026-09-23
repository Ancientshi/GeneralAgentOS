"""Runs in a fresh interpreter; upstream imports cannot collide across benchmarks.

This file is intentionally standard-library-only until an evaluator is selected.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def read(path):
    return json.loads(Path(path).read_text())


def score(metrics, feedback=None):
    return {"status": "completed", "metrics": metrics, "feedback": feedback or []}


def dare(ctx, root, submission, output, route):
    evaluator = module(root / "scripts/evaluation.py", "official_dare")
    data = ctx["private"]
    result = evaluator.evaluate_prediction(
        str(submission / "prediction.csv"),
        data["gold"],
        data["metadata"],
        ctx["task"]["variant"],
    )
    (output / "raw.json").write_text(json.dumps(result, indent=2))
    if result.get("error"):
        return {"status": "invalid_submission", "metrics": {}, "feedback": [result["error"]]}
    return score(
        {
            "final_score": result["final_score"],
            **{f"target:{k}": v for k, v in result.get("per_target_scores", {}).items()},
        },
        ["Scored by the upstream DARE evaluator; higher is better (0–1)."],
    )


def coda(ctx, root, submission, output, route):
    sys.path.insert(0, str(root))
    from coda_bench.evaluation import evaluate

    row = ctx["private"]["row"]
    # The public release omits data_path on some rows; the official evaluator only
    # consumes these fields. Keep its scoring logic unchanged.
    task = SimpleNamespace(**row)
    prediction = SimpleNamespace(
        instance_id=row["instance_id"], prediction=(submission / "answer.txt").read_text()
    )
    result = evaluate([task], [prediction]).to_dict()
    (output / "raw.json").write_text(json.dumps(result, indent=2))
    return score(
        {"exact_accuracy": result["exact_accuracy"], "numeric_accuracy": result["numeric_accuracy"]},
        ["Official exact and numeric matching, restricted to the selected instance."],
    )


def ddr(ctx, root, submission, output, route):
    sys.path.insert(0, str(root))
    from evaluate.unified_evaluator import UnifiedEvaluator

    data = ctx["private"]
    insights = read(submission / "insights.json")
    if not isinstance(insights, list) or not insights or not all(isinstance(x, str) for x in insights):
        return {
            "status": "invalid_submission",
            "metrics": {},
            "feedback": ["insights.json must be a nonempty list of strings"],
        }
    evaluator = UnifiedEvaluator(
        scenario=data["scenario"],
        provider=route.get("provider", "openai"),
        openai_model=route["model"],
        azure_model=route["model"],
        max_retries=route.get("max_retries", 2),
    )
    qa = evaluator.load_qa_data(data["qa"])[data["entity"]]
    result = evaluator.evaluate_entity(
        data["entity"], qa, "\n\n".join(insights), (submission / "report.md").read_text(), insights
    )
    (output / "raw.json").write_text(json.dumps(result, indent=2))
    stats = result["summary"]
    if not stats or any(x["api_failed"] or x["errors"] for x in stats.values()):
        return {
            "status": "evaluator_error",
            "metrics": {},
            "feedback": ["Judge returned missing or failed judgments; no score reported"],
        }
    return score(
        {f"{key}.correct_percentage": x["correct_percentage"] for key, x in stats.items()},
        [f"Official DDR checklist evaluation with {route['model']}; percentages range from 0 to 100."],
    )


def ambig_target(ctx, root, submission, output, route):
    data = ctx["private"]
    manifest = data["manifest"]
    # Model always submits id,prediction. Hidden original names are restored here.
    with (submission / "submission.csv").open() as f:
        rows = list(csv.DictReader(f))
    with Path(data["gold"]).open() as f:
        gold = list(csv.DictReader(f))
    if not rows or not gold or set(rows[0]) != {"id", "prediction"}:
        return {
            "status": "invalid_submission",
            "metrics": {},
            "feedback": ["Use submission.csv columns id,prediction"],
        }
    target = manifest["task"]["original_target_name"]
    identifiers = [c for c in gold[0] if c != target]
    if len(identifiers) != 1:
        raise ValueError("Configure a task-specific evaluator for a multi-key Ambig submission")
    key = identifiers[0]
    by_id = {r["id"]: r["prediction"] for r in rows}
    if len(by_id) != len(rows) or set(by_id) != {r[key] for r in gold}:
        return {
            "status": "invalid_submission",
            "metrics": {},
            "feedback": ["Submission IDs must match every test row exactly once"],
        }
    converted = output / "submission-native.csv"
    with converted.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[key, target])
        writer.writeheader()
        writer.writerows({key: r[key], target: by_id[r[key]]} for r in gold)
    task_id = ctx["task"]["task_id"]
    (output / task_id).mkdir()
    subprocess.run(
        [
            sys.executable,
            data["script"],
            "--answer_file",
            data["gold"],
            "--predict_file",
            str(converted),
            "--path",
            str(output),
            "--name",
            task_id,
        ],
        check=True,
    )
    metric = float((output / task_id / "result.txt").read_text().strip())
    return score(
        {"competition_metric": metric},
        [
            "Original DSBench task metric; its scale and direction are competition-specific.",
            "This score does not by itself measure clarification quality or prove which target was chosen.",
        ],
    )


def ambig_objective(ctx, root, submission, output, route):
    from mlebench.grade import grade_csv
    from mlebench.registry import Registry

    registry = Registry(data_dir=Path(ctx["private"]["mle_data"]))
    competition = registry.get_competition(ctx["task"]["task_id"])
    report = grade_csv(submission / "submission.csv", competition)
    (output / "raw.json").write_text(json.dumps(report.to_dict(), indent=2, default=str))
    if not report.valid_submission:
        return {
            "status": "invalid_submission",
            "metrics": {},
            "feedback": ["MLE-bench rejected the submission"],
        }
    return score(
        {"competition_metric": float(report.score)},
        [
            "Original MLE-bench competition metric; "
            + ("lower" if report.is_lower_better else "higher")
            + " is better.",
            "The metric score alone is not a clarification-policy or framing-diagnostic score.",
        ],
    )


def dacomp_da(ctx, root, submission, output, route):
    suite = root / "dacomp-da/evaluation_suite"
    sys.path.insert(0, str(suite))
    task_id = ctx["task"]["task_id"]
    language = ctx["private"].get("language", "en")
    native = output / "agent_results/gaos" / task_id
    shutil.copytree(submission, native)
    shutil.copyfile(native / "report.md", native / f"{task_id}.md")
    shutil.copyfile(native / "trajectory.txt", native / f"{task_id}-traj.txt")
    metadata = Path(route.get("metadata_root", str(suite / ("src" if language == "en" else "src_zh"))))
    scores_dir = output / "scores"
    subprocess.run(
        [
            sys.executable,
            str(suite / "llm_judge.py"),
            "--inputs",
            str(native.parent),
            "--rubrics-model",
            route["model"],
            "--gsb-model-text",
            route.get("text_model", route["model"]),
            "--gsb-model-vis",
            route.get("vision_model", route["model"]),
            "--max-workers",
            "1",
            "--metadata-root",
            str(metadata),
            "--output-dir",
            str(scores_dir),
            "--language",
            language,
        ],
        cwd=suite,
        check=True,
    )
    from core.rubric_scoring import compute_file_score, load_metadata_scores

    files = list(scores_dir.glob("*.csv"))
    if len(files) != 1:
        raise ValueError("Expected a single task score file from DAComp")
    result = compute_file_score(files[0], load_metadata_scores([metadata]), {task_id})
    (output / "raw.json").write_text(json.dumps(result, indent=2))
    required = [
        "weighted_total",
        "rubric_completeness",
        "rubric_accuracy",
        "rubric_conclusiveness",
        "gsb_readability",
        "gsb_professionalism",
        "gsb_visualization",
    ]
    if any(not result.get(k) or result[k][0] is None or result[k][1] != 1 for k in required):
        raise ValueError("Missing DAComp judge dimensions; refusing partial score")
    return score(
        {k: float(result[k][0]) for k in required},
        ["Official DAComp aggregation; original dimension scales retained."],
    )


def dacomp_de(ctx, root, submission, output, route):
    suite = root / "dacomp-de/evaluation_suite"
    sys.path.insert(0, str(suite))
    import utils

    # run.py has already run in the gold-free agent sandbox at submission time.
    # Never execute candidate Python in the trusted evaluator process.
    utils.execute_run_py = lambda pred_dir, database_file, force_rebuild=False: (
        Path(pred_dir) / database_file
    ).is_file()
    task_id = ctx["task"]["task_id"]
    native = output / "predictions" / task_id
    shutil.copytree(submission / "project", native)
    evaluator = utils.PipelineEvaluator(
        route.get("config", str(suite / "evaluation_config_compare.yaml")), force_rebuild=False, mode="cfs"
    )
    result = evaluator.evaluate_example(
        task_id, route.get("gold_dir", str(suite / "gold")), str(native.parent)
    )
    (output / "raw.json").write_text(json.dumps(result, indent=2))
    return score(
        {"cfs": result["final_score"]},
        [
            "Official CFS comparison after isolated run.py execution; CS mode is not enabled in this adapter.",
            f"Evaluation level: {result.get('evaluation_level', 'unknown')}",
        ],
    )


def dacomp_arch(ctx, root, submission, output, route):
    suite = root / "dacomp-de/evaluation_suite_arch"
    sys.path.insert(0, str(suite))
    evaluator_module = module(suite / "evaluate.py", "official_arch")
    task_id = ctx["task"]["task_id"]
    native = output / "blueprints"
    native.mkdir()
    shutil.copyfile(submission / "architecture.yaml", native / f"{task_id}.yaml")
    evaluator = evaluator_module.DEDEvaluator(
        eval_model=route["model"],
        project_path=str(native),
        max_workers=1,
        gold_en_jsonl=str(suite / "gold/dacomp-arch-gold.jsonl"),
        gold_zh_jsonl=str(suite / "gold/dacomp-arch-zh-gold.jsonl"),
    )
    result = evaluator.evaluate_single_task(str(native), task_id)
    (output / "raw.json").write_text(json.dumps(result, indent=2))
    if "error" in result or result.get("max_score", 0) <= 0:
        raise ValueError("Architecture judge failed")
    return score({"actual_score": result["actual_score"], "max_score": result["max_score"]})


ROUTES = {
    "dare": dare,
    "coda": coda,
    "ddr": ddr,
    "ambig-target": ambig_target,
    "ambig-objective": ambig_objective,
    "dacomp-da": dacomp_da,
    "dacomp-de": dacomp_de,
    "dacomp-arch": dacomp_arch,
}


def main():
    ctx = read(sys.argv[1])
    output_file = Path(ctx["output"])
    result = ROUTES[ctx["evaluator"]](
        ctx, Path(ctx["private"]["root"]), Path(ctx["submission"]), output_file.parent, ctx["route"]
    )
    if any(not math.isfinite(v) for v in result.get("metrics", {}).values()):
        raise ValueError("Non-finite official score")
    output_file.write_text(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
