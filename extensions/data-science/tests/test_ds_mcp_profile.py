import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("online", [False, True])
def test_resource_mcp_discovery_and_render(online):
    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "gaos_ds", "serve"] + (["--online"] if online else [])
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {
                    "ds_get_resource",
                    "ds_search_resources",
                    "ds_list_recipes",
                    "ds_render_recipe",
                    "ds_recommend",
                } <= names
                assert ("ds_search_hub" in names) == online
                result = await session.call_tool(
                    "ds_render_recipe",
                    {
                        "recipe_id": "profile-csv",
                        "parameters": {"input_path": "input.csv"},
                    },
                )
                assert not result.is_error
                assert "template_sha256" in str(result)

    anyio.run(exercise)


def test_composed_profile_with_two_mcp_services(tmp_path, monkeypatch):
    pytest.importorskip("general_agent_os")
    import yaml
    from agno.skills import LocalSkills, Skills
    from fastapi.testclient import TestClient
    from general_agent_os.profile import load_profile
    from general_agent_os.runtime import create_app

    base = Path(__file__).resolve().parents[1]
    paths = [base / "skills", base.parent / "benchmarks/skills"]
    skills = Skills(loaders=[LocalSkills(str(path)) for path in paths])
    assert len(skills.get_skill_names()) == 7
    data = yaml.safe_load((base / "profile.yaml").read_text())
    data["agents"]["data-scientist"]["skill_list"] = list(map(str, paths))
    data["agents"]["data-scientist"]["storage_db"] = str(tmp_path / "sessions.db")
    (tmp_path / "benchmarks.yaml").write_text("schema_version: 1\nbenchmarks: {}\n")
    for entry in data["mcp_servers"].values():
        entry.update(command=sys.executable, cwd=str(tmp_path))
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(data))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-no-model-call")
    monkeypatch.delenv("GAOS_API_KEY", raising=False)
    with TestClient(create_app(load_profile([profile]))) as client:
        assert client.get("/health").status_code == 200
        assert any(agent["id"] == "data-scientist" for agent in client.get("/agents").json())
