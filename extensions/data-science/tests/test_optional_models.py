"""Real CPU smoke tests, skipped when the optional model dependencies are absent."""

import json

import numpy as np
import pandas as pd
import pytest

from gaos_ds.recipes import render_recipe


def test_catboost_actual_fit(tmp_path, monkeypatch):
    pytest.importorskip("catboost")
    monkeypatch.chdir(tmp_path)
    train = pd.DataFrame(
        {"id": np.arange(80), "x": np.arange(80), "kind": ["a", "b"] * 40, "label": [0, 1] * 40}
    )
    test = pd.DataFrame({"id": [91, 83], "x": [10, 11], "kind": ["unseen", None]})
    train.to_csv("train.csv", index=False)
    test.to_csv("test.csv", index=False)
    result = render_recipe(
        "tabular-catboost",
        {
            "train_path": "train.csv",
            "test_path": "test.csv",
            "target": "label",
            "features": ["x", "kind"],
            "problem": "classification",
            "split": "random",
            "id_column": "id",
            "iterations": 10,
        },
    )
    exec(compile(result["code"], "<authored-catboost-recipe>", "exec"), {})
    output = pd.read_csv("predictions.csv")
    assert output.id.tolist() == [91, 83]
    assert set(output.prediction) <= {0, 1}
    receipt = json.loads((tmp_path / "predictions.csv.receipt.json").read_text())
    assert receipt["package_versions"]["catboost"] != "not-installed"


def test_statsforecast_actual_fit(tmp_path, monkeypatch):
    pytest.importorskip("statsforecast")
    monkeypatch.chdir(tmp_path)
    history = pd.DataFrame(
        {
            "series": ["a"] * 40 + ["b"] * 40,
            "time": list(pd.date_range("2024-01-01", periods=40)) * 2,
            "value": list(10 + np.sin(np.arange(40))) + list(20 + np.cos(np.arange(40))),
        }
    )
    history.to_csv("history.csv", index=False)
    result = render_recipe(
        "forecast-statsforecast",
        {
            "input_path": "history.csv",
            "id_column": "series",
            "time_column": "time",
            "target": "value",
            "frequency": "D",
            "horizon": 3,
        },
    )
    exec(compile(result["code"], "<authored-statsforecast-recipe>", "exec"), {})
    output = pd.read_csv("forecast.csv")
    assert len(output) == 6
    assert set(output.unique_id) == {"a", "b"}
    assert np.isfinite(output.prediction).all()
    assert pd.to_datetime(output.ds).min() > history.time.max()
