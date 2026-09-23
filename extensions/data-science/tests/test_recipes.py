import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from gaos_ds.catalog import catalog, recommend, search_resources
from gaos_ds.recipes import RECIPES, render_recipe


def execute_recipe(monkeypatch, tmp_path, recipe_id, parameters):
    monkeypatch.chdir(tmp_path)
    result = render_recipe(recipe_id, parameters)
    # Authored, deterministic library templates on synthetic data; no model-generated program.
    exec(compile(result["code"], "<test-recipe>", "exec"), {})
    return result


def tabular_fixture(tmp_path):
    n = 80
    frame = pd.DataFrame(
        {
            "id": np.arange(n),
            "x": np.arange(n, dtype=float),
            "category": ["a", "b"] * (n // 2),
            "y": np.arange(n) % 2,
            "date": pd.date_range("2024-01-01", periods=n // 2).repeat(2),
            "group": np.repeat(np.arange(20), 4),
        }
    )
    frame.loc[3:5, "x"] = np.nan
    frame.to_csv(tmp_path / "train.csv", index=False)
    test = frame.iloc[[7, 3, 9]].copy()
    test["category"] = ["previously-unseen", "a", "b"]
    test["y"] = 999  # A test target must never be used in fitting or diagnostics.
    test.to_csv(tmp_path / "test.csv", index=False)
    return (
        frame,
        test,
        {
            "train_path": "train.csv",
            "test_path": "test.csv",
            "target": "y",
            "features": ["x", "category"],
            "problem": "classification",
            "split": "random",
            "id_column": "id",
        },
    )


def test_catalog_and_recipe_links():
    cards = catalog()
    assert len(cards) == 24
    assert len({entry["id"] for entry in cards}) == len(cards)
    for entry in cards:
        assert entry["docs_url"].startswith("https://")
        assert set(entry["recipes"]) <= RECIPES.keys()
    assert search_resources("分类", capability="classification")
    ranked = recommend("classification", "dare-bench", gpu=False)
    assert ranked["candidates"][0]["compute"] == "cpu"
    with pytest.raises(ValueError):
        recommend("made-up")


@pytest.mark.parametrize("mode", ["random", "group", "time"])
def test_tabular_split_and_submission_alignment(tmp_path, monkeypatch, mode):
    frame, test, config = tabular_fixture(tmp_path)
    config["split"] = mode
    if mode != "random":
        config["time_column" if mode == "time" else "group_column"] = "date" if mode == "time" else "group"
    result = execute_recipe(monkeypatch, tmp_path, "tabular-sklearn", config)
    prediction = pd.read_csv(tmp_path / "predictions.csv")
    assert prediction.id.tolist() == test.id.tolist()
    assert set(prediction.prediction) <= {0, 1}
    receipt = json.loads((tmp_path / "predictions.csv.receipt.json").read_text())
    assert receipt["template_sha256"] == result["template_sha256"]
    assert receipt["official_benchmark_score"] is False
    diagnostics = receipt["diagnostics"]
    fit, valid = diagnostics["fit_row_indices"], diagnostics["validation_row_indices"]
    assert set(fit).isdisjoint(valid)
    assert set(fit) | set(valid) == set(range(len(frame)))
    if mode == "time":
        assert frame.iloc[fit].date.max() < frame.iloc[valid].date.min()
    if mode == "group":
        assert set(frame.iloc[fit].group).isdisjoint(frame.iloc[valid].group)


def test_regression_random_forest_and_feature_exclusion(tmp_path, monkeypatch):
    _, _, config = tabular_fixture(tmp_path)
    config.update(problem="regression", model="random-forest")
    execute_recipe(monkeypatch, tmp_path, "tabular-sklearn", config)
    receipt = json.loads((tmp_path / "predictions.csv.receipt.json").read_text())
    assert "mae" in receipt["diagnostics"]["validation"]
    config["features"] = ["id", "y"]
    with pytest.raises(ValueError, match="excluding target"):
        execute_recipe(monkeypatch, tmp_path, "tabular-sklearn", config)


def test_validation_preprocessing_does_not_see_holdout(tmp_path, monkeypatch):
    from sklearn.impute import SimpleImputer

    observed_fit_lengths = []
    original = SimpleImputer.fit

    def tracked(self, x, y=None):
        observed_fit_lengths.append(len(x))
        return original(self, x, y)

    monkeypatch.setattr(SimpleImputer, "fit", tracked)
    _, _, config = tabular_fixture(tmp_path)
    execute_recipe(monkeypatch, tmp_path, "tabular-sklearn", config)
    assert observed_fit_lengths == [64, 64, 80, 80]


def test_forecast_uses_history_and_checks_frequency(tmp_path, monkeypatch):
    history = pd.DataFrame(
        {"series": ["a"] * 20, "time": pd.date_range("2024-01-01", periods=20), "value": [1, 2] * 10}
    )
    history.to_csv(tmp_path / "history.csv", index=False)
    config = {
        "input_path": "history.csv",
        "id_column": "series",
        "time_column": "time",
        "target": "value",
        "frequency": "D",
        "horizon": 4,
        "season_length": 2,
    }
    execute_recipe(monkeypatch, tmp_path, "forecast-seasonal", config)
    result = pd.read_csv(tmp_path / "forecast.csv")
    assert result.prediction.tolist() == [1, 2, 1, 2]
    assert pd.to_datetime(result.ds).min() > history.time.max()
    receipt = json.loads((tmp_path / "forecast.csv.receipt.json").read_text())
    assert receipt["diagnostics"]["validation"]["mae"] == 0
    history.drop(index=4).to_csv(tmp_path / "history.csv", index=False)
    with pytest.raises(ValueError, match="frequency"):
        execute_recipe(monkeypatch, tmp_path, "forecast-seasonal", config)


def test_profile_and_welch_effect_direction(tmp_path, monkeypatch):
    data = pd.DataFrame(
        {"group": ["control"] * 4 + ["treatment"] * 4, "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]}
    )
    data.to_csv(tmp_path / "data.csv", index=False)
    execute_recipe(monkeypatch, tmp_path, "profile-csv", {"input_path": "data.csv"})
    assert json.loads((tmp_path / "profile.json").read_text())["diagnostics"]["rows"] == 8
    execute_recipe(
        monkeypatch,
        tmp_path,
        "compare-groups",
        {
            "input_path": "data.csv",
            "group_column": "group",
            "value_column": "value",
            "group_a": "treatment",
            "group_b": "control",
        },
    )
    report = json.loads((tmp_path / "comparison.json").read_text())["diagnostics"]
    assert report["mean_a_minus_b"] == 4
    assert report["confidence_interval_95"][0] > 0
    assert report["p_value"] < 0.05


def test_sqlite_schema_quoted_table_and_no_mutation(tmp_path, monkeypatch):
    import hashlib

    path = tmp_path / "data.sqlite"
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE "strange""table" (id INTEGER PRIMARY KEY, value REAL)')
        db.execute('INSERT INTO "strange""table" VALUES (1, 2.0)')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    execute_recipe(monkeypatch, tmp_path, "sqlite-inspect", {"input_path": "data.sqlite"})
    report = json.loads((tmp_path / "schema.json").read_text())["diagnostics"]
    assert report["tables"][0]["rows"] == 1
    assert before == hashlib.sha256(path.read_bytes()).hexdigest()


def test_render_is_data_only_and_validates_paths(tmp_path, monkeypatch):
    tricky = "a'); raise RuntimeError('injection'); #.csv"
    pd.DataFrame({"x": [1]}).to_csv(tmp_path / tricky, index=False)
    execute_recipe(monkeypatch, tmp_path, "profile-csv", {"input_path": tricky})
    for params in (
        {"input_path": "../outside.csv"},
        {"input_path": "/private/data.csv"},
        {"input_path": "x.csv", "output": "x.csv"},
        {"input_path": "x.csv", "typo": 1},
    ):
        with pytest.raises(ValueError):
            render_recipe("profile-csv", params)
    (tmp_path / "alias.csv").symlink_to(tmp_path / tricky)
    with pytest.raises(ValueError, match="overwrite"):
        execute_recipe(monkeypatch, tmp_path, "profile-csv", {"input_path": tricky, "output": "alias.csv"})


@pytest.mark.parametrize("recipe_id", RECIPES)
def test_every_template_compiles_with_declared_parameters(recipe_id):
    values = {
        "train_path": "train.csv",
        "test_path": "test.csv",
        "input_path": "data.csv",
        "target": "y",
        "features": ["x"],
        "problem": "regression",
        "split": "random",
        "id_column": "id",
        "time_column": "date",
        "horizon": 4,
        "frequency": "D",
        "group_column": "group",
        "value_column": "x",
        "group_a": "a",
        "group_b": "b",
        "model_path": "/models/checkpoint",
        "metric": "root_mean_squared_error",
    }
    parameters = {
        key: values[key] for key, spec in RECIPES[recipe_id]["parameters"].items() if spec["required"]
    }
    rendered = render_recipe(recipe_id, parameters)
    compile(rendered["preflight_code"], "<preflight>", "exec")
    compile(rendered["code"], "<code>", "exec")
