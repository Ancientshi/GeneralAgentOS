import sys
from pathlib import Path

import pytest
import yaml


def test_mcp_stdio_tool_discovery_and_catalog(tmp_path):
    pytest.importorskip("mcp")
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    config = tmp_path / "benchmarks.yaml"
    config.write_text("schema_version: 1\nbenchmarks: {}\n")

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "gaos_bench", "--config", str(config), "serve"]
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()
                names = {t.name for t in response.tools}
                assert names == {
                    "list_benchmarks",
                    "list_tasks",
                    "get_task",
                    "start_run",
                    "read_file",
                    "write_file",
                    "execute_python",
                    "submit_run",
                    "run_status",
                }
                result = await session.call_tool("list_benchmarks", {})
                assert not result.is_error

    anyio.run(exercise)


def test_profile_loads_skill_and_mcp_through_existing_runtime(tmp_path, monkeypatch):
    pytest.importorskip("general_agent_os")
    from agno.skills import LocalSkills, Skills
    from fastapi.testclient import TestClient

    from general_agent_os.profile import load_profile
    from general_agent_os.runtime import create_app

    base = Path(__file__).resolve().parents[1]
    skills = Skills(loaders=[LocalSkills(str(base / "skills"))])
    assert "benchmark-runner" in skills.get_skill_names()
    config = tmp_path / "benchmarks.yaml"
    config.write_text("schema_version: 1\nbenchmarks: {}\n")
    data = yaml.safe_load((base / "profile.yaml").read_text())
    data["agents"]["benchmark-agent"]["skill_list"] = [str(base / "skills")]
    data["agents"]["benchmark-agent"]["storage_db"] = str(tmp_path / "sessions.db")
    data["mcp_servers"]["benchmarks"].update(
        command=sys.executable, cwd=str(tmp_path), args=["-m", "gaos_bench", "--config", str(config), "serve"]
    )
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(data))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-no-network")
    monkeypatch.delenv("GAOS_API_KEY", raising=False)
    app = create_app(load_profile([profile]))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/agents")
        assert response.status_code == 200
        assert any(a["id"] == "benchmark-agent" for a in response.json())
