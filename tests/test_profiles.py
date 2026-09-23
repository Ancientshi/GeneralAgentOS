import os
from pathlib import Path

import pytest
import yaml

from general_agent_os.cli import main
from general_agent_os.profile import ProfileError, load_profile
from general_agent_os.runtime import create_app


def test_composition_and_relative_paths(profile_factory, tmp_path, monkeypatch):
    source = profile_factory()
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        "agents:\n  assistant:\n    instructions: Changed\n    model_options:\n      temperature: 0.1\n"
    )
    monkeypatch.chdir(tmp_path.parent)
    profile = load_profile([source, overlay])
    assert profile.data["agents"]["assistant"]["instructions"] == "Changed"
    assert profile.data["agents"]["assistant"]["model"] == "test-model"
    assert profile.path("data/test.db") == tmp_path / "data/test.db"


@pytest.mark.parametrize(
    "changes,match",
    [
        ({"agents": {"assistant": {"modle": "wrong"}}}, "unsupported options"),
        ({"agents": {"assistant": {"mcp_list": ["missing"]}}}, "not defined"),
        ({"agents": {"assistant": {"mcp_list": "bad"}}}, "must be a list"),
        ({"agents": {"assistant": {"reasoning": True}}}, "explicit reasoning"),
        ({"agents": {"assistant": {"reasoning_agent": "assistant"}}}, "cycle"),
        ({"agents": {"assistant": {"api_key": "must-not-appear-in-errors"}}}, "api_key_env"),
        ({"agents": {"assistant": {"skill_list": ["missing"]}}}, "does not exist"),
        ({"agents": {"assistant": {"provider": "typo"}}}, "unsupported provider"),
        ({"agents": {"assistant": {"model_options": {"api_key": "private"}}}}, "cannot override"),
        ({"os": {"port": 99999}}, "between"),
        ({"schema_version": 2}, "schema_version"),
    ],
)
def test_reject_invalid_profiles(profile_factory, changes, match):
    with pytest.raises(ProfileError, match=match):
        load_profile([profile_factory(**changes)])


def test_env_missing_and_default(profile_factory, monkeypatch):
    monkeypatch.delenv("GAOS_TEST_MISSING", raising=False)
    path = profile_factory(agents={"assistant": {"instructions": "${GAOS_TEST_MISSING}"}})
    with pytest.raises(ProfileError, match="GAOS_TEST_MISSING"):
        load_profile([path])
    path = profile_factory(agents={"assistant": {"instructions": "${GAOS_TEST_MISSING:-fallback}"}})
    assert load_profile([path]).data["agents"]["assistant"]["instructions"] == "fallback"


def test_renamed_fields(profile_factory):
    path = profile_factory(agents={"assistant": {"enable_user_memories": True}})
    cfg = load_profile([path]).data["agents"]["assistant"]
    assert cfg["update_memory_on_run"] is True
    assert "enable_user_memories" not in cfg


def test_no_network_during_validation(profile_factory, monkeypatch):
    import socket

    monkeypatch.setattr(socket.socket, "connect", lambda *a: pytest.fail("Validation opened a connection"))
    main(["validate", "-p", str(profile_factory())])


def test_non_loopback_requires_key(profile_factory):
    with pytest.raises(ProfileError, match="non-loopback"):
        create_app(load_profile([profile_factory(os={"host": "0.0.0.0"})]))


def test_init_does_not_overwrite(tmp_path):
    path = tmp_path / "new-agent"
    main(["init", str(path)])
    assert "GAOS_API_KEY=" in (path / ".env").read_text()
    assert os.stat(path / ".env").st_mode & 0o777 == 0o600
    with pytest.raises(SystemExit):
        main(["init", str(path)])


def test_import_legacy(tmp_path):
    old = tmp_path / "old.yaml"
    old.write_text(
        yaml.safe_dump(
            {
                "id": "old",
                "model": "test-model",
                "provider": "VLLM",
                "port": 8123,
                "reasoning": False,
                "knowledge_list": None,
            }
        )
    )
    output = tmp_path / "new.yaml"
    main(["import-legacy", "-c", str(old), "--output", str(output), "--base-url", "http://localhost:8000/v1"])
    profile = load_profile([output])
    assert profile.data["os"]["port"] == 8123
    assert profile.data["agents"]["assistant"]["id"] == "old"


def test_all_self_contained_examples(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("MODEL_ID", "test")
    monkeypatch.setenv("MCP_URL", "https://example.com/mcp")
    monkeypatch.setenv("MCP_TOKEN", "test")
    for name in ("assistant", "vllm", "multi-agent", "mcp"):
        load_profile([root / "examples" / f"{name}.yaml"])
