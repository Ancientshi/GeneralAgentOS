"""Shared helpers copied into standalone recipes; no extension import is needed in the sandbox."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd


def local_path(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Data/output paths must be relative to the execution workspace")
    root = Path.cwd().resolve()
    if not path.resolve().is_relative_to(root):
        raise ValueError("Path escapes the execution workspace")
    return path


def read_csv(value):
    return pd.read_csv(local_path(value))


def write_json(value, data):
    path = local_path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False, default=str) + "\n")


def digest(value):
    hasher = hashlib.sha256()
    with local_path(value).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def receipt(config, inputs, diagnostics):
    versions = {}
    for package in RECIPE_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    weights = {}
    if config.get("model_path"):
        model_path = Path(config["model_path"])
        paths = (
            [model_path] if model_path.is_file() else sorted(p for p in model_path.rglob("*") if p.is_file())
        )
        for path in paths:
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
            weights[path.name if model_path.is_file() else str(path.relative_to(model_path))] = (
                hasher.hexdigest()
            )
    return {
        "recipe": RECIPE_ID,
        "template_sha256": TEMPLATE_SHA256,
        "parameters": config,
        "input_sha256": {p: digest(p) for p in inputs},
        "package_versions": versions,
        "model_file_sha256": weights,
        "diagnostics": diagnostics,
        "official_benchmark_score": False,
    }


def validate_outputs(config):
    inputs = {
        local_path(config[key]).resolve()
        for key in ("input_path", "train_path", "test_path")
        if key in config
    }
    outputs = {
        local_path(config["output"]).resolve(),
        local_path(config["output"] + ".receipt.json").resolve(),
    }
    if inputs & outputs:
        raise ValueError("Output would overwrite an input file")
    if "model_dir" in config and local_path(config["model_dir"]).exists():
        raise ValueError("Use a fresh model_dir for this attempt")


def output_path(config):
    path = local_path(config["output"])
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def tabular_data(config):
    from sklearn.model_selection import GroupShuffleSplit, train_test_split

    train, test = read_csv(config["train_path"]), read_csv(config["test_path"])
    target, features = config["target"], config["features"]
    forbidden = {target, config["id_column"], config["group_column"], config["time_column"]} - {""}
    if not features or len(features) != len(set(features)) or forbidden.intersection(features):
        raise ValueError("Provide unique feature names excluding target, ID and split columns")
    for frame in (train, test):
        if not set(features).issubset(frame.columns):
            raise ValueError("Some selected features are absent from a data file")
    if target not in train or train[target].isna().any():
        raise ValueError("Training target is absent or contains missing values")
    if len(train) < 10 or len(test) == 0:
        raise ValueError("Need at least 10 training rows and a nonempty test file")
    problem = config["problem"]
    if problem == "regression" and not np.isfinite(pd.to_numeric(train[target])).all():
        raise ValueError("Regression target must be finite numeric values")
    ids = config["id_column"]
    if ids and (ids not in test or test[ids].isna().any() or test[ids].duplicated().any()):
        raise ValueError("Test IDs must be present, non-null and unique")
    rows = np.arange(len(train))
    mode = config["split"]
    fraction = config["validation_fraction"]
    if mode == "time":
        if not config["time_column"]:
            raise ValueError("Time split requires time_column")
        stamps = pd.to_datetime(train[config["time_column"]], errors="raise")
        if stamps.isna().any():
            raise ValueError("Missing timestamps")
        # A timestamp must never appear on both sides of the cutoff.
        unique = np.sort(stamps.unique())
        if len(unique) < 2:
            raise ValueError("Time split needs multiple distinct timestamps")
        cut = max(1, min(len(unique) - 1, int(len(unique) * (1 - fraction))))
        fit_rows, valid_rows = rows[stamps < unique[cut]], rows[stamps >= unique[cut]]
    elif mode == "group":
        column = config["group_column"]
        if not column or train[column].isna().any():
            raise ValueError("Group split requires a non-null group_column")
        splitter = GroupShuffleSplit(n_splits=1, test_size=fraction, random_state=config["seed"])
        fit_rows, valid_rows = next(splitter.split(train, groups=train[column]))
    else:
        if config["time_column"] or config["group_column"]:
            raise ValueError("Choose time/group split when its column is specified")
        stratify = train[target] if problem == "classification" else None
        fit_rows, valid_rows = train_test_split(
            rows, test_size=fraction, random_state=config["seed"], stratify=stratify
        )
    if min(len(fit_rows), len(valid_rows)) < 2:
        raise ValueError("Validation and fitting subsets must have at least two rows")
    if problem == "classification" and train.iloc[fit_rows][target].nunique() < 2:
        raise ValueError("Fitting subset must contain at least two classes")
    return train, test, fit_rows, valid_rows


def tabular_finish(config, train, test, fit_rows, valid_rows, model_factory):
    from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, r2_score

    features, target = config["features"], config["target"]
    fitting, validation = train.iloc[fit_rows], train.iloc[valid_rows]
    model = model_factory(fitting, validation, "validation")
    predicted = np.asarray(model.predict(validation[features])).reshape(-1)
    if config["problem"] == "classification":
        metrics = {
            "accuracy": accuracy_score(validation[target], predicted),
            "macro_f1": f1_score(validation[target], predicted, average="macro", zero_division=0),
        }
    else:
        metrics = {
            "mae": mean_absolute_error(validation[target], predicted),
            "r2": r2_score(validation[target], predicted),
        }
    # Fresh model and fresh preprocessing; held-out validation never participates in its own fit.
    final = model_factory(train, None, "final")
    prediction = np.asarray(final.predict(test[features])).reshape(-1)
    result = pd.DataFrame({config["prediction_column"]: prediction})
    if config["id_column"]:
        result.insert(0, config["id_column"], test[config["id_column"]].to_numpy())
    result.to_csv(output_path(config), index=False)
    info = receipt(
        config,
        [config["train_path"], config["test_path"]],
        {
            "validation": metrics,
            "fit_row_indices": fit_rows.tolist(),
            "validation_row_indices": valid_rows.tolist(),
            "test_rows": len(test),
            "output_kind": "class-labels" if config["problem"] == "classification" else "point-predictions",
            "note": "Internal holdout metrics only. Probability submissions require a separate adapter.",
        },
    )
    write_json(config["output"] + ".receipt.json", info)
    print(json.dumps(info["diagnostics"]))


def forecast_data(config):
    data = read_csv(config["input_path"])
    id_col, time_col, target = config["id_column"], config["time_column"], config["target"]
    frame = data[[id_col, time_col, target]].rename(
        columns={id_col: "unique_id", time_col: "ds", target: "y"}
    )
    if frame.isna().any().any():
        raise ValueError("Forecast input has missing IDs, timestamps or targets; clean explicitly")
    frame["ds"] = pd.to_datetime(frame["ds"], errors="raise")
    frame["y"] = pd.to_numeric(frame["y"], errors="raise")
    if not np.isfinite(frame["y"]).all() or frame.duplicated(["unique_id", "ds"]).any():
        raise ValueError("Non-finite targets or duplicate (series, time) keys")
    frame = frame.sort_values(["unique_id", "ds"])
    for _, group in frame.groupby("unique_id", sort=False):
        if len(group) <= config["horizon"] + config["season_length"]:
            raise ValueError("Each series needs more history than horizon + season_length")
        expected = pd.date_range(group["ds"].iloc[0], periods=len(group), freq=config["frequency"])
        if not np.array_equal(expected.to_numpy(), group["ds"].to_numpy()):
            raise ValueError("Timestamps do not match the explicit frequency; resample deliberately")
    return frame


def forecast_finish(config, frame, forecast_function):
    horizon = config["horizon"]
    fit = frame.groupby("unique_id", group_keys=False).head(-horizon)
    holdout = frame.groupby("unique_id", group_keys=False).tail(horizon)
    valid = forecast_function(fit, horizon)
    joined = holdout.merge(valid, on=["unique_id", "ds"], how="left", validate="one_to_one")
    if len(joined) != len(holdout) or joined["prediction"].isna().any():
        raise ValueError("Forecast did not match every held-out timestamp")
    errors = joined["y"] - joined["prediction"]
    result = forecast_function(frame, horizon)
    result.to_csv(output_path(config), index=False)
    info = receipt(
        config,
        [config["input_path"]],
        {
            "validation": {"mae": float(errors.abs().mean()), "rmse": float(np.sqrt((errors**2).mean()))},
            "validation_scheme": "last horizon timestamps of each series; same horizon as final prediction",
            "output_columns": result.columns.tolist(),
            "series": int(frame.unique_id.nunique()),
            "note": "Generic forecast output; adapt column names and row order to the selected benchmark.",
        },
    )
    write_json(config["output"] + ".receipt.json", info)
    print(json.dumps(info["diagnostics"]))
