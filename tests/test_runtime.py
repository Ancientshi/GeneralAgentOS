import asyncio
import socket
import sys

from fastapi.testclient import TestClient

from general_agent_os.deploy import deploy, status, stop
from general_agent_os.profile import load_profile
from general_agent_os.runtime import build_tools, create_app


def test_real_api_model_and_persistent_history(profile_factory, model_server, monkeypatch):
    url, requests = model_server
    monkeypatch.setenv("GAOS_API_KEY", "test-service-key")
    path = profile_factory(agents={"assistant": {"base_url": url, "add_history_to_context": True}})
    # The fixture clears the key while creating its profile, so set it after construction.
    monkeypatch.setenv("GAOS_API_KEY", "test-service-key")
    profile = load_profile([path])
    auth = {"Authorization": "Bearer test-service-key"}
    with TestClient(create_app(profile)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/agents").status_code == 401
        assert client.get("/agents", headers={"Authorization": "Bearer wrong"}).status_code == 401
        agents = client.get("/agents", headers=auth)
        assert agents.status_code == 200
        response = client.post(
            "/agents/assistant/runs",
            headers=auth,
            data={"message": "Hello", "stream": "false", "session_id": "test-session"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["content"] == "Profile works."
        stream = client.post(
            "/agents/assistant/runs",
            headers=auth,
            data={"message": "Again", "stream": "true", "session_id": "test-session"},
        )
        assert stream.status_code == 200, stream.text
        assert "Profile works." in stream.text
    assert len(requests) == 2
    assert any(m.get("content") == "Hello" for m in requests[1]["messages"])
    # A new application instance must read the persisted history.
    app = create_app(profile)
    session = app.state.gaos.agents[0].db.get_session(session_id="test-session")
    assert session is not None
    assert len(session.runs) == 2


def test_stdio_mcp_connection_and_shutdown(profile_factory, tmp_path):
    server = tmp_path / "mcp_server.py"
    server.write_text(
        'from fastmcp import FastMCP\nmcp = FastMCP("test")\n'
        "@mcp.tool()\ndef add(a: int, b: int) -> int:\n    return a + b\n"
        'if __name__ == "__main__":\n    mcp.run()\n'
    )
    profile = load_profile(
        [
            profile_factory(
                agents={"assistant": {"mcp_list": ["math"]}},
                mcp_servers={"math": {"command": sys.executable, "args": [str(server)]}},
            )
        ]
    )

    async def run():
        tool = build_tools(profile, profile.data["agents"]["assistant"])[0]
        async with tool:
            assert "add" in tool.functions
            result = await tool.session.call_tool("add", {"a": 2, "b": 3})
            assert "5" in str(result)

    asyncio.run(run())
    with TestClient(create_app(profile)) as client:
        assert client.get("/health").status_code == 200


def test_detached_deployment_health_and_stop(profile_factory, tmp_path, monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    monkeypatch.setenv("GAOS_STATE_DIR", str(tmp_path / "state"))
    profile = load_profile([profile_factory(os={"port": port})])
    try:
        result = deploy(profile, "test-deployment")
        assert result["running"]
        assert status("test-deployment")["running"]
    finally:
        stop("test-deployment")
    assert not status("test-deployment")["running"]
