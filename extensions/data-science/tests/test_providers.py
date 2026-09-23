import io
import json
from types import SimpleNamespace

import pytest

from gaos_ds import providers


def test_hf_filters_response_and_encodes_query(monkeypatch):
    requests = []
    payload = [
        {
            "id": "owner/model",
            "sha": "abc",
            "downloads": 3,
            "cardData": {"license": "apache-2.0"},
            "tags": ["tabular"],
            "private_field": "not copied",
        }
    ]

    class Opener:
        def open(self, req, timeout):
            requests.append(req.full_url)
            return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(providers.urllib.request, "build_opener", lambda *_: Opener())
    result = providers.search_hub("huggingface", "models", "tabular & time", 1)
    assert result["status"] == "ok"
    assert "search=tabular+%26+time" in requests[0]
    assert result["items"][0]["revision"] == "abc"
    assert "private_field" not in result["items"][0]


def test_hf_unavailable_is_not_empty_success(monkeypatch):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise OSError("secret-bearing body")

    monkeypatch.setattr(providers.urllib.request, "build_opener", lambda *_: Opener())
    result = providers.search_hub("huggingface", "datasets", "forecasting")
    assert result["status"] == "unavailable"
    assert "secret-bearing" not in json.dumps(result)


def test_kaggle_fixed_read_only_command(monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda _: "/env/bin/kaggle")
    observed = []

    def run(args, **kwargs):
        observed.extend(args)
        kwargs["stdout"].write(b"ref,title,secret\nauthor/data,Example,not-copied\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(providers.subprocess, "run", run)
    result = providers.search_hub("kaggle", "datasets", "--mine; rm -rf /", 2)
    assert observed == ["/env/bin/kaggle", "datasets", "list", "--search=--mine; rm -rf /", "--csv"]
    assert result["items"][0]["url"] == "https://www.kaggle.com/datasets/author/data"
    assert "secret" not in result["items"][0]


def test_kaggle_setup_and_provider_validation(monkeypatch):
    monkeypatch.setattr(providers.shutil, "which", lambda _: None)
    assert providers.search_hub("kaggle", "models", "tabular")["status"] == "setup-required"
    with pytest.raises(ValueError):
        providers.search_hub("https://arbitrary-site", "models", "test")
    with pytest.raises(ValueError):
        providers.search_hub("kaggle", "notebooks", "test")
