from __future__ import annotations

import hashlib
import json
from importlib.resources import files


def field(kind, description, *, default=None, required=False, choices=None, minimum=None, maximum=None):
    return dict(
        type=kind,
        description=description,
        default=default,
        required=required,
        choices=choices,
        minimum=minimum,
        maximum=maximum,
    )


TEXT = lambda description: field("string", description, required=True)  # noqa: E731
TABULAR = {
    "train_path": TEXT("Workspace-relative training CSV with observed targets"),
    "test_path": TEXT("Workspace-relative prediction CSV; any target column is ignored"),
    "target": TEXT("Explicit target column from the public task"),
    "features": field(
        "array", "Explicit predictor columns; excludes IDs, target, split columns", required=True
    ),
    "problem": field("string", "Task type", required=True, choices=["classification", "regression"]),
    "split": field(
        "string", "Public training data validation design", required=True, choices=["random", "group", "time"]
    ),
    "id_column": field("string", "Optional identifier copied in test row order", default=""),
    "prediction_column": field(
        "string", "Output prediction column; class labels, not probabilities", default="prediction"
    ),
    "time_column": field("string", "Timestamp for time split; never used as a raw predictor", default=""),
    "group_column": field("string", "Entity for group split; never used as a predictor", default=""),
    "validation_fraction": field(
        "number", "Internal validation fraction", default=0.2, minimum=0.05, maximum=0.5
    ),
    "seed": field("integer", "Random seed", default=42, minimum=0, maximum=2147483647),
    "output": field("string", "Workspace-relative prediction CSV", default="predictions.csv"),
}
FORECAST = {
    "input_path": TEXT("Workspace-relative history CSV, excluding future target values"),
    "id_column": TEXT("Series identifier column"),
    "time_column": TEXT("Timestamp column"),
    "target": TEXT("Observed time-series target column"),
    "frequency": TEXT("Explicit pandas frequency such as D or MS"),
    "horizon": field("integer", "Forecast horizon in time steps", required=True, minimum=1, maximum=10000),
    "season_length": field(
        "integer", "Seasonal period; 1 for a last-value baseline", default=1, minimum=1, maximum=10000
    ),
    "output": field("string", "Workspace-relative forecast CSV", default="forecast.csv"),
}
WEIGHTS = {
    "model_path": TEXT(
        "Operator-prepared local model file or snapshot directory available inside the sandbox"
    ),
    "device": field(
        "string",
        "CPU works with the default runner; CUDA requires a GPU-capable runner",
        default="cpu",
        choices=["cpu", "cuda"],
    ),
}


def recipe(template, description, parameters, packages, tested=False):
    return {
        "template": template,
        "description": description,
        "parameters": parameters,
        "packages": packages,
        "validation_status": "executed-on-synthetic-fixture"
        if tested
        else "template-only-optional-dependencies",
    }


RECIPES = {
    "profile-csv": recipe(
        "profile_csv",
        "Audit missingness, duplicates, types and numeric ranges",
        {
            "input_path": TEXT("Workspace-relative CSV"),
            "output": field("string", "Report JSON", default="profile.json"),
        },
        ["numpy", "pandas"],
        True,
    ),
    "sqlite-inspect": recipe(
        "sqlite_inspect",
        "Read-only schema and row counts for all SQLite tables",
        {
            "input_path": TEXT("Workspace-relative SQLite database"),
            "output": field("string", "Report JSON", default="schema.json"),
        },
        ["numpy", "pandas"],
        True,
    ),
    "compare-groups": recipe(
        "compare_groups",
        "Independent-groups Welch comparison with effect and interval",
        {
            "input_path": TEXT("Workspace-relative CSV"),
            "group_column": TEXT("Column identifying groups"),
            "value_column": TEXT("Numeric outcome column"),
            "group_a": TEXT("First group label, as string"),
            "group_b": TEXT("Second group label, as string"),
            "output": field("string", "Report JSON", default="comparison.json"),
        },
        ["numpy", "pandas", "scipy"],
        True,
    ),
    "tabular-sklearn": recipe(
        "tabular_sklearn",
        "Leakage-aware linear or random-forest baseline",
        {
            **TABULAR,
            "model": field(
                "string", "Estimator family", default="linear", choices=["linear", "random-forest"]
            ),
        },
        ["numpy", "pandas", "scikit-learn"],
        True,
    ),
    "tabular-catboost": recipe(
        "tabular_catboost",
        "Optional local CatBoost with native category handling",
        {
            **TABULAR,
            "iterations": field("integer", "Boosting iterations", default=200, minimum=1, maximum=5000),
        },
        ["numpy", "pandas", "scikit-learn", "catboost"],
        True,
    ),
    "tabular-autogluon": recipe(
        "tabular_autogluon",
        "Optional bounded AutoGluon RF/XT ensemble",
        {
            **TABULAR,
            "metric": TEXT(
                "AutoGluon metric chosen from the public task, e.g. f1_macro or root_mean_squared_error"
            ),
            "time_limit": field(
                "integer", "Seconds per fit; there are two fits", default=60, minimum=10, maximum=3600
            ),
            "model_dir": field(
                "string", "Fresh workspace-relative model output directory", default="autogluon-models"
            ),
        },
        ["numpy", "pandas", "scikit-learn", "autogluon.tabular"],
    ),
    "tabular-tabpfn": recipe(
        "tabular_tabpfn",
        "Optional TabPFN from an explicit local checkpoint",
        {
            **TABULAR,
            **WEIGHTS,
        },
        ["numpy", "pandas", "scikit-learn", "tabpfn"],
    ),
    "forecast-seasonal": recipe(
        "forecast_seasonal",
        "Seasonal-naive forecast and chronological holdout",
        FORECAST,
        ["numpy", "pandas"],
        True,
    ),
    "forecast-statsforecast": recipe(
        "forecast_statsforecast",
        "Optional AutoARIMA and chronological holdout",
        FORECAST,
        ["numpy", "pandas", "statsforecast"],
        True,
    ),
    "forecast-chronos": recipe(
        "forecast_chronos",
        "Optional univariate Chronos-2 from a local snapshot",
        {
            **FORECAST,
            **WEIGHTS,
        },
        ["numpy", "pandas", "chronos-forecasting"],
    ),
}


def list_recipes() -> list[dict]:
    return [{"id": key, **value} for key, value in RECIPES.items()]


def render_recipe(recipe_id: str, parameters: dict) -> dict:
    if recipe_id not in RECIPES:
        raise ValueError(f"Unknown recipe: {recipe_id}")
    recipe = RECIPES[recipe_id]
    schema = recipe["parameters"]
    if set(parameters) - set(schema):
        raise ValueError(f"Unknown parameters: {sorted(set(parameters) - set(schema))}")
    config = {}
    for key, spec in schema.items():
        if key not in parameters and spec["required"]:
            raise ValueError(f"Missing required parameter: {key}")
        value = parameters.get(key, spec["default"])
        kind = spec["type"]
        valid = (
            (kind == "string" and isinstance(value, str))
            or (kind == "integer" and type(value) is int)
            or (kind == "number" and type(value) in (int, float))
            or (
                kind == "array"
                and isinstance(value, list)
                and value
                and all(isinstance(item, str) and item for item in value)
            )
        )
        if not valid or (spec["required"] and value == ""):
            raise ValueError(f"Invalid {kind} parameter: {key}")
        if spec["choices"] and value not in spec["choices"]:
            raise ValueError(f"{key} must be one of {spec['choices']}")
        if spec["minimum"] is not None and not spec["minimum"] <= value <= spec["maximum"]:
            raise ValueError(f"{key} is outside its allowed range")
        config[key] = value
    if config.get("id_column") and config["id_column"] == config.get("prediction_column"):
        raise ValueError("Prediction column and ID column must differ")
    if recipe_id == "compare-groups" and config["group_a"] == config["group_b"]:
        raise ValueError("Choose two different groups")
    from pathlib import PurePosixPath

    for key in ("input_path", "train_path", "test_path", "output", "model_dir"):
        if key in config:
            path = PurePosixPath(config[key])
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError(f"{key} must be a workspace-relative path")
    inputs = {
        str(PurePosixPath(config[key])) for key in ("input_path", "train_path", "test_path") if key in config
    }
    if {
        str(PurePosixPath(config["output"])),
        str(PurePosixPath(config["output"] + ".receipt.json")),
    } & inputs:
        raise ValueError("Output would overwrite an input")
    root = files("gaos_ds").joinpath("templates")
    source = (
        root.joinpath("common.py").read_text() + "\n" + root.joinpath(recipe["template"] + ".py").read_text()
    )
    checksum = hashlib.sha256(source.encode()).hexdigest()
    header = (
        f"# Portable GAOS data-science recipe: {recipe_id}\n"
        f"RECIPE_ID = {recipe_id!r}\nTEMPLATE_SHA256 = {checksum!r}\n"
        f"RECIPE_PACKAGES = {recipe['packages']!r}\n"
    )
    # JSON is encoded as a Python string literal, never interpolated as executable code.
    code = (
        header
        + source
        + f"\nCONFIG = json.loads({json.dumps(config, ensure_ascii=False, allow_nan=False)!r})\nvalidate_outputs(CONFIG)\nrun(CONFIG)\n"
    )
    compile(code, f"<recipe:{recipe_id}>", "exec")
    preflight = (
        "import importlib.metadata, json\nresult = {}\n"
        f"for package in {recipe['packages']!r}:\n"
        "    try: result[package] = importlib.metadata.version(package)\n"
        "    except importlib.metadata.PackageNotFoundError: result[package] = 'MISSING'\n"
        "print(json.dumps(result))\n"
    )
    return {
        "recipe_id": recipe_id,
        "template_sha256": checksum,
        "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "parameters": config,
        "packages": recipe["packages"],
        "validation_status": recipe["validation_status"],
        "preflight_code": preflight,
        "code": code,
        "execution": "Pass preflight_code then code to the selected sandbox executor; this tool does not execute or install anything.",
        "outputs": [config["output"]]
        + ([config["output"] + ".receipt.json"] if "train_path" in config or "horizon" in config else []),
    }
