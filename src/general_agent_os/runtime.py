"""Build AgentOS 3 objects; AgentOS owns MCP connect/close lifecycle."""

from __future__ import annotations

import os
import secrets

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat
from agno.os import AgentOS
from starlette.responses import JSONResponse

from . import __version__
from .models import VLLMChat
from .profile import AGENT_FIELDS, Profile, ProfileError


def build_model(cfg: dict):
    options = dict(cfg.get("model_options", {}))
    for key in ("extra_body", "request_params"):
        if key in cfg:
            options[key] = cfg[key]
    provider = cfg.get("provider", "openai")
    env_name = cfg.get("api_key_env", "OPENAI_API_KEY" if provider == "openai" else "MODEL_API_KEY")
    api_key = os.getenv(env_name)
    if not api_key:
        raise ProfileError(f"Missing model credential environment variable: {env_name}")
    if provider == "vllm":
        options.setdefault("provider", "VLLM")
        options.setdefault("name", "VLLM")
        return VLLMChat(id=cfg["model"], base_url=cfg.get("base_url"), api_key=api_key, **options)
    return OpenAIChat(id=cfg["model"], base_url=cfg.get("base_url"), api_key=api_key, **options)


def build_tools(profile: Profile, cfg: dict) -> list:
    names = cfg.get("mcp_list") or []
    if not names:
        return []
    try:
        from agno.tools.mcp import MCPTools
        from mcp import StdioServerParameters
    except ImportError:
        raise ProfileError('MCP support needs the extra: pip install "general-agent-os[mcp]"') from None
    tools = []
    for name in names:
        server = profile.data["mcp_servers"][name]
        options = dict(
            name=name,
            timeout_seconds=server.get("timeout_seconds", cfg.get("timeout_seconds", 30)),
            include_tools=cfg.get("include_tools"),
            exclude_tools=cfg.get("exclude_tools"),
            tool_name_prefix=server.get("tool_name_prefix"),
        )
        if "command" in server:
            options["server_params"] = StdioServerParameters(
                command=server["command"],
                args=server.get("args", []),
                cwd=str(profile.path(server.get("cwd", "."))),
                env={**os.environ, **{k: str(v) for k, v in server.get("env", {}).items()}},
            )
            options["transport"] = "stdio"
        else:
            options.update(
                url=server["url"],
                transport=server.get("transport", "streamable-http"),
                headers=server.get("headers"),
            )
        tools.append(MCPTools(**options))
    return tools


def build_database(profile: Profile, name: str, cfg: dict):
    path = profile.path(cfg.get("storage_db", f"data/{name}.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteDb(
        id=cfg.get("db_id", f"{name}-db"),
        db_file=str(path),
        session_table=cfg.get("storage_table", "agno_sessions"),
    )


def build_knowledge(profile: Profile, name: str, cfg: dict):
    spec = cfg.get("knowledge")
    if not spec:
        return None
    from agno.knowledge.embedder.openai import OpenAIEmbedder
    from agno.knowledge.knowledge import Knowledge

    try:
        from agno.vectordb.chroma import ChromaDb
    except ImportError:
        raise ProfileError("Knowledge requires the [knowledge] extra") from None
    return Knowledge(
        vector_db=ChromaDb(
            collection=spec.get("collection", name),
            path=str(profile.path(spec.get("path", "data/knowledge"))),
            persistent_client=True,
            embedder=OpenAIEmbedder(id=spec.get("embedder", "text-embedding-3-small")),
        )
    )


class BearerAuth:
    """Protect HTTP and WebSocket access with a shared deployment key."""

    def __init__(self, app, key: str):
        self.app, self.key = app, key

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            public = scope.get("path") == "/health" and scope.get("method") in {"GET", "HEAD"}
            if not public and scope.get("method") != "OPTIONS":
                headers = dict(scope.get("headers", []))
                supplied = headers.get(b"authorization", b"").decode("latin1")
                if not secrets.compare_digest(supplied, f"Bearer {self.key}"):
                    if scope["type"] == "websocket":
                        await send({"type": "websocket.close", "code": 1008})
                    else:
                        await JSONResponse(
                            {"detail": "Unauthorized"},
                            status_code=401,
                            headers={"WWW-Authenticate": "Bearer"},
                        )(scope, receive, send)
                    return
        await self.app(scope, receive, send)


def create_app(profile: Profile):
    settings = profile.data["os"]
    key_env = settings.get("api_key_env", "GAOS_API_KEY")
    key = os.getenv(key_env)
    if settings.get("host", "127.0.0.1") not in {"127.0.0.1", "localhost", "::1"} and not key:
        raise ProfileError(f"Set {key_env} before binding to a non-loopback address")
    agents = {}

    def build(name):
        if name in agents:
            return agents[name]
        cfg = profile.data["agents"][name]
        options = {k: v for k, v in cfg.items() if k not in AGENT_FIELDS}
        options.setdefault("markdown", True)
        options.setdefault("telemetry", False)
        if cfg.get("reasoning_model"):
            reasoning = cfg["reasoning_model"]
            options["reasoning_model"] = (
                build_model({**cfg, "model": reasoning})
                if isinstance(reasoning, str)
                else build_model(reasoning)
            )
        if cfg.get("reasoning_agent"):
            options["reasoning_agent"] = build(cfg["reasoning_agent"])
        if cfg.get("skill_list"):
            from agno.skills import LocalSkills, Skills

            options["skills"] = Skills(loaders=[LocalSkills(str(profile.path(p))) for p in cfg["skill_list"]])
        agents[name] = Agent(
            model=build_model(cfg),
            tools=build_tools(profile, cfg),
            db=build_database(profile, name, cfg),
            knowledge=build_knowledge(profile, name, cfg),
            **options,
        )
        return agents[name]

    for name in profile.data["agents"]:
        build(name)
    agent_os = AgentOS(
        id=settings.get("id", "general-agent-os"),
        name=settings.get("name", "General Agent OS"),
        description=settings.get("description", "Profile-driven agents"),
        version=__version__,
        agents=list(agents.values()),
        cors_allowed_origins=settings.get("cors_origins", []),
        telemetry=False,
    )
    app = agent_os.get_app()
    if key:
        app.add_middleware(BearerAuth, key=key)
    app.state.gaos = agent_os
    return app
