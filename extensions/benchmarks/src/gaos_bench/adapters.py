"""Translate upstream releases into public tasks and evaluator-only metadata.

Only explicitly selected inputs are staged; repositories and gold files never are.
"""

from __future__ import annotations

import json

from .common import BenchError, Config, Task, read_json, safe_path, validate_id

SOURCES = {
    "dare-bench": "https://github.com/Snowflake-Labs/dare-bench",
    "coda-bench": "https://github.com/ruc-datalab/CoDA-Bench",
    "ddr-bench": "https://github.com/thinkwee/DDR_Bench",
    "dacomp": "https://github.com/ByteDance-Seed/DAComp",
    "ambig-ds": "https://huggingface.co/datasets/anonymous222bit/Ambig-DS-T",
}


def dare(config, spec):
    root = config.resolve(spec["root"])
    index = root / spec.get("index", "data/eval/question_list.json")
    for row in read_json(index):
        task_id = validate_id(row["file_path"])
        folder = safe_path(root / "data/eval/databases", task_id)
        for variant in ("v1", "v2"):
            kind = row["task"]
            if kind == "time_series_analysis":
                gold = f"ground_truth_{variant}.csv"
                tag = "XF" if variant == "v1" else "CF"
            else:
                gold = "simulated_pred_local.csv" if variant == "v1" else "ground_truth.csv"
                tag = "IF" if variant == "v1" else "MM"
            files = row[f"needed_files_{variant}"]
            yield Task(
                "dare-bench",
                task_id,
                variant,
                row[f"question_{variant}"],
                "dare",
                ["prediction.csv"],
                [(safe_path(folder / "source", f), f) for f in files],
                {
                    "root": str(root),
                    "gold": str(folder / "verify" / gold),
                    "metadata": str(folder / "verify/all_metadata.json"),
                    "kind": kind,
                    "reference_receipt": str(folder / "verify/gaos-reference.json"),
                },
                [kind, tag],
            )


def coda(config, spec):
    root = config.resolve(spec["root"])
    index = root / spec.get("index", "data/coda_bench.json")
    communities = config.resolve(spec.get("communities", str(root / "datasets/communities")))
    for row in read_json(index):
        community = validate_id(row["release_community"])
        yield Task(
            "coda-bench",
            validate_id(row["instance_id"]),
            "default",
            row["question"] + "\n\n" + row.get("answer_guidelines", ""),
            "coda",
            ["answer.txt"],
            [(safe_path(communities, f"{community}/full_community"), "data")],
            {"root": str(root), "row": row},
            ["file-discovery", community],
        )


def ddr(config, spec):
    root = config.resolve(spec["root"])
    for scenario in ("10k", "mimic", "globem"):
        ids = root / "data" / scenario / "entity_ids.json"
        if not ids.exists():
            continue
        scenario_spec = spec.get("scenarios", {}).get(scenario, {})
        asset = config.resolve(scenario_spec.get("data", f"missing-data/{scenario}"))
        dest = "data" if scenario == "globem" else "data/database.sqlite"
        nouns = {"10k": "company (CIK)", "mimic": "patient", "globem": "user"}
        for entity in read_json(ids):
            task_id = validate_id(f"{scenario}-{entity}")
            prompt = (
                f"Explore the supplied {scenario} data for {nouns[scenario]} {entity}. "
                "Discover and substantiate useful insights through analysis. Choose your own research "
                "questions; there is no predefined question to answer. Save distinct evidence-backed "
                "insights as a JSON list of strings in insights.json and a final report in report.md."
            )
            yield Task(
                "ddr-bench",
                task_id,
                "default",
                prompt,
                "ddr",
                ["insights.json", "report.md"],
                [(asset, dest)],
                {
                    "root": str(root),
                    "entity": str(entity),
                    "scenario": scenario,
                    "qa": str(root / "data" / scenario / "qa.json"),
                },
                ["open-ended-analysis", scenario],
            )


def ambig(config, spec):
    root = config.resolve(spec["root"])
    prepared = config.resolve(spec.get("prepared", str(root / "prepared")))
    gold_root = config.resolve(spec.get("gold", str(root / "gold")))
    for folder in sorted((root / "tasks").glob("*")):
        if not (folder / "_manifest.json").exists():
            continue
        manifest = read_json(folder / "_manifest.json")
        task_id = validate_id(folder.name)
        for variant, filename in (("full", "task.txt"), ("ambiguous", "task_ambig.txt")):
            data = prepared / task_id / variant
            # Explicit allowlist: never stage a manifest, full prompt or test answer.
            yield Task(
                "ambig-ds",
                task_id,
                variant,
                (folder / filename).read_text(),
                "ambig-target",
                ["submission.csv"],
                [(data / "train.csv", "data/train.csv"), (data / "test.csv", "data/test.csv")],
                {
                    "root": str(root),
                    "script": str(folder / "eval.py"),
                    "gold": str(gold_root / task_id / "test_answer.csv"),
                    "manifest": manifest,
                },
                ["target", manifest["task"]["task_type"]],
            )
    objective_root = config.resolve(spec.get("objective_root", str(root.parent / "Ambig-DS-M")))
    index = objective_root / "task_list.txt"
    if index.exists():
        mle_data = config.resolve(spec.get("mle_data", "datasets/mle"))
        for slug in index.read_text().splitlines():
            if not slug.strip():
                continue
            task_id = validate_id(slug.strip())
            for variant, filename in (
                ("objective-full", "full.md"),
                ("objective-ambiguous", "ambig_metric.md"),
            ):
                prompt = (objective_root / "prompts" / task_id / filename).read_text()
                yield Task(
                    "ambig-ds",
                    task_id,
                    variant,
                    prompt,
                    "ambig-objective",
                    ["submission.csv"],
                    [(mle_data / task_id / "prepared/public", "data")],
                    {
                        "root": str(objective_root),
                        "mle_data": str(mle_data),
                        "gold": str(mle_data / task_id / "prepared/private"),
                    },
                    ["objective"],
                )
    # Specialized protocols can also use the explicit manifest contract.
    if spec.get("manifest"):
        yield from manifest_tasks(config, {**spec, "benchmark": "ambig-ds"})


def dacomp(config, spec):
    root = config.resolve(spec["root"])
    da_data = config.resolve(spec.get("da_data", str(root / "dacomp-da/tasks")))
    da_index = da_data / spec.get("da_index", "dacomp-da.jsonl")
    if da_index.exists():
        for line in da_index.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            task_id = validate_id(row["instance_id"])
            yield Task(
                "dacomp",
                task_id,
                "da",
                row["instruction"],
                "dacomp-da",
                ["report.md", "trajectory.txt"],
                [(safe_path(da_data, task_id), "data")],
                {"root": str(root), "language": spec.get("language", "en")},
                ["analysis"],
            )
    de_data = config.resolve(spec.get("de_data", str(root / "dacomp-de/tasks")))
    for folder in sorted(de_data.glob("dacomp-de-*")):
        if not folder.is_dir() or not any(s in folder.name for s in ("-impl-", "-evol-")):
            continue
        task_id = validate_id(folder.name)
        kind = "de-impl" if "-impl-" in task_id else "de-evol"
        question = folder / "question.md"
        prompt = (
            question.read_text()
            if question.exists()
            else (
                "Implement the complete SQL data pipeline in project/ according to docs/data_contract.yaml "
                "and config/layer_dependencies.yaml. Complete run.py so it builds the required DuckDB database."
            )
        )
        yield Task(
            "dacomp",
            task_id,
            kind,
            prompt,
            "dacomp-de",
            ["project"],
            [(folder, "project")],
            {"root": str(root)},
            ["engineering", kind],
        )
    arch = root / "dacomp-de/evaluation_suite_arch/gold" / spec.get("arch_index", "dacomp-arch-gold.jsonl")
    if arch.exists():
        for line in arch.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            task_id = validate_id(row["id"])
            yield Task(
                "dacomp",
                task_id,
                "de-arch",
                row["question"],
                "dacomp-arch",
                ["architecture.yaml"],
                [],
                {"root": str(root)},
                ["engineering", "architecture"],
            )


def manifest_tasks(config, spec):
    """An operator-controlled escape hatch for new suites; never an agent tool."""
    path = config.resolve(spec["manifest"])
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        inputs = [(config.resolve(x["source"]), x["destination"]) for x in row.get("inputs", [])]
        for _, dest in inputs:
            safe_path(path.parent, dest)
        yield Task(
            spec["benchmark"],
            validate_id(row["task_id"]),
            row.get("variant", "default"),
            row["prompt"],
            row["evaluator"],
            row["artifacts"],
            inputs,
            row.get("private", {}),
            row.get("tags", []),
        )


ADAPTERS = {"dare-bench": dare, "coda-bench": coda, "ddr-bench": ddr, "ambig-ds": ambig, "dacomp": dacomp}


def tasks(config: Config, name: str):
    spec = config.spec(name)
    loader = ADAPTERS.get(spec.get("adapter", name))
    if spec.get("adapter") == "manifest":
        result = list(manifest_tasks(config, {**spec, "benchmark": name}))
    elif loader:
        result = list(loader(config, spec))
    else:
        raise BenchError(f"Unknown adapter: {name}")
    keys = [(t.task_id, t.variant) for t in result]
    if len(set(keys)) != len(keys):
        raise BenchError(f"Duplicate task IDs and variants in {name}")
    return result


def select(config, name, task_id, variant=None):
    matches = [
        t
        for t in tasks(config, name)
        if t.task_id == str(task_id) and (variant is None or t.variant == variant)
    ]
    if not matches:
        raise BenchError(f"Unknown task or variant: {name}/{task_id}/{variant}")
    if len(matches) > 1:
        raise BenchError("Choose a variant: " + ", ".join(t.variant for t in matches))
    return matches[0]
