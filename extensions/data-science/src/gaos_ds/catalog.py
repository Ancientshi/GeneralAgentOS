from __future__ import annotations

import json
from importlib.resources import files

CAPABILITIES = {
    "classification",
    "regression",
    "forecasting",
    "exploration",
    "statistics",
    "explanation",
    "causal",
    "engineering",
    "discovery",
    "clustering",
}
BENCHMARKS = {"ambig-ds", "dare-bench", "ddr-bench", "coda-bench", "dacomp"}


def catalog() -> list[dict]:
    return json.loads(files("gaos_ds").joinpath("resources.json").read_text(encoding="utf-8"))


def get_resource(resource_id: str) -> dict:
    for entry in catalog():
        if entry["id"] == resource_id:
            return entry
    raise ValueError(f"Unknown resource: {resource_id}")


def search_resources(query: str = "", capability: str = "", limit: int = 20) -> list[dict]:
    if capability and capability not in CAPABILITIES:
        raise ValueError(f"capability must be one of {sorted(CAPABILITIES)}")
    tokens = query.casefold().split()
    matches = []
    for entry in catalog():
        haystack = json.dumps(entry, ensure_ascii=False).casefold()
        if capability and capability not in entry["capabilities"]:
            continue
        if all(token in haystack for token in tokens):
            matches.append(entry)
    return matches[: max(1, min(limit, 50))]


def recommend(capability: str, benchmark: str = "", gpu: bool = False) -> dict:
    """Explain suitability, not a learned ranking or a claim of benchmark performance."""
    if benchmark and benchmark not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark: {benchmark}")
    entries = search_resources(capability=capability, limit=50)
    if not capability:
        raise ValueError("An explicit capability is required; do not infer a hidden target or metric")
    ranked = []
    for entry in entries:
        score = int(bool(entry["recipes"])) * 2 + int(benchmark in entry["benchmark_fit"])
        if entry["compute"] == "gpu-recommended" and not gpu:
            score -= 3
        ranked.append((score, entry))
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
    return {
        "method": "capability match; prefer available recipes and CPU options when no GPU is supplied",
        "candidates": [entry for _, entry in ranked],
        "protocol_notes": [
            "Suitability is our integration judgment, not evidence that the benchmark authors used this resource.",
            "Follow the public task's mandated method; DARE instruction-following tasks may forbid substitution.",
            "Resolve target, metric, time horizon and permitted external resources before selecting a model.",
            "Local validation is diagnostic; only the benchmark evaluator produces an official score.",
        ],
    }
