"""Load, compose and validate portable YAML profiles without opening network connections."""

from __future__ import annotations

import copy
import inspect
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ProfileError(ValueError):
    pass


def deep_merge(target: dict, source: dict) -> dict:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
    return target


ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def interpolate(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: interpolate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v) for v in value]
    if not isinstance(value, str):
        return value

    def replace(match):
        name, default = match.groups()
        resolved = os.environ.get(name) or default
        if resolved is None:
            raise ProfileError(f"Missing environment variable: {name}")
        return resolved

    return ENV_PATTERN.sub(replace, value)


@dataclass
class Profile:
    data: dict
    root: Path
    files: list[Path]

    def path(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else self.root / path


def load_profile(files: list[str | Path]) -> Profile:
    if not files:
        raise ProfileError("Provide at least one YAML profile.")
    paths = [Path(f).expanduser().resolve() for f in files]
    merged: dict = {}
    for path in paths:
        part = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(part, dict):
            raise ProfileError(f"{path.name}: top level must be a mapping")
        deep_merge(merged, part)
    profile = Profile(interpolate(merged), paths[0].parent, paths)
    validate_profile(profile)
    return profile


AGENT_FIELDS = {
    "provider",
    "model",
    "base_url",
    "api_key_env",
    "model_options",
    "extra_body",
    "request_params",
    "storage_db",
    "storage_table",
    "db_id",
    "skill_list",
    "knowledge",
    "mcp_list",
    "include_tools",
    "exclude_tools",
    "timeout_seconds",
    "reasoning_model",
    "reasoning_agent",
    "reasoning",
    "reasoning_min_steps",
    "reasoning_max_steps",
    "port",
}
RENAMED = {
    "enable_user_memories": "update_memory_on_run",
    "search_session_history": "search_past_sessions",
    "num_history_sessions": "num_past_sessions_to_search",
    "num_past_session_runs": "num_past_session_runs_in_search",
    "response_model": "output_schema",
}
PROVIDERS = {"openai", "openai-compatible", "vllm", "proxyllm", "siliconflow", "jacobapi"}


def validate_profile(profile: Profile) -> None:
    from agno.agent import Agent

    data = profile.data
    if data.get("schema_version", 1) != 1:
        raise ProfileError("Unsupported schema_version; expected 1")
    unknown = set(data) - {"schema_version", "os", "agents", "mcp_servers"}
    if unknown:
        raise ProfileError(f"Unknown profile fields: {', '.join(sorted(unknown))}")
    settings = data.setdefault("os", {})
    if not isinstance(settings, dict):
        raise ProfileError("os must be a mapping")
    unknown = set(settings) - {
        "id", "name", "description", "host", "port", "cors_origins", "api_key_env",
        "authorization", "jwt_verification_key_file",
    }
    if unknown:
        raise ProfileError(f"Unknown os fields: {', '.join(sorted(unknown))}")
    if not isinstance(settings.get("authorization", False), bool):
        raise ProfileError("os.authorization must be a boolean")
    if "jwt_verification_key_file" in settings:
        if not settings.get("authorization"):
            raise ProfileError("os.jwt_verification_key_file requires os.authorization: true")
        value = settings["jwt_verification_key_file"]
        if not isinstance(value, str) or not value.strip():
            raise ProfileError("os.jwt_verification_key_file must be a non-empty path")
    try:
        port = int(settings.get("port", 7777))
    except (ValueError, TypeError):
        raise ProfileError("os.port must be an integer") from None
    if not 1 <= port <= 65535:
        raise ProfileError("os.port must be between 1 and 65535")
    settings["port"] = port
    agents = data.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise ProfileError("agents must be a non-empty mapping")
    servers = data.setdefault("mcp_servers", {})
    if not isinstance(servers, dict):
        raise ProfileError("mcp_servers must be a mapping")
    for name, server in servers.items():
        if not isinstance(server, dict) or bool(server.get("command")) == bool(server.get("url")):
            raise ProfileError(f"MCP {name}: provide exactly one of command or url")
        allowed = {
            "command",
            "args",
            "cwd",
            "env",
            "url",
            "transport",
            "headers",
            "timeout_seconds",
            "tool_name_prefix",
        }
        if set(server) - allowed:
            raise ProfileError(f"MCP {name}: unknown fields {sorted(set(server) - allowed)}")
        if server.get("url") and server.get("transport", "streamable-http") not in {"sse", "streamable-http"}:
            raise ProfileError(f"MCP {name}: unsupported HTTP transport")
        if server.get("command") and server.get("transport", "stdio") != "stdio":
            raise ProfileError(f"MCP {name}: command requires stdio transport")
        if "args" in server and (
            not isinstance(server["args"], list) or not all(isinstance(a, str) for a in server["args"])
        ):
            raise ProfileError(f"MCP {name}: args must be a list of strings")
    accepted = set(inspect.signature(Agent).parameters)
    # These require Python objects and cannot be populated with raw YAML.
    reserved = {"db", "tools", "skills", "knowledge", "agent_id", "team_id"}
    ids: set[str] = set()
    for name, cfg in agents.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            raise ProfileError("Agent names must use letters, numbers, dots, underscores or hyphens")
        if not isinstance(cfg, dict):
            raise ProfileError(f"Agent {name}: configuration must be a mapping")
        for old, new in RENAMED.items():
            if old in cfg:
                if new in cfg:
                    raise ProfileError(f"Agent {name}: use only {new}, not both {old} and {new}")
                cfg[new] = cfg.pop(old)
        if not isinstance(cfg.get("model"), str) or not cfg["model"].strip():
            raise ProfileError(f"Agent {name}: model is required")
        cfg["provider"] = str(cfg.get("provider", "openai")).lower()
        if cfg["provider"] not in PROVIDERS:
            raise ProfileError(f"Agent {name}: unsupported provider {cfg['provider']}")
        if cfg["provider"] != "openai" and not cfg.get("base_url"):
            raise ProfileError(f"Agent {name}: base_url is required for {cfg['provider']}")
        if "api_key" in cfg:
            raise ProfileError(f"Agent {name}: use api_key_env instead of embedding a credential")
        for section in ("model_options", "request_params", "extra_body"):
            if section in cfg and not isinstance(cfg[section], dict):
                raise ProfileError(f"Agent {name}: {section} must be a mapping")
        if set(cfg.get("model_options", {})) & {"id", "api_key", "base_url"}:
            raise ProfileError(f"Agent {name}: model_options cannot override id, api_key or base_url")
        unknown = set(cfg) - ((accepted - reserved) | AGENT_FIELDS)
        if unknown:
            raise ProfileError(f"Agent {name}: unsupported options: {', '.join(sorted(unknown))}")
        agent_id = cfg.setdefault("id", name)
        if not isinstance(agent_id, str) or not agent_id or agent_id in ids:
            raise ProfileError(f"Agent {name}: id must be a unique, non-empty string")
        ids.add(agent_id)
        cfg.setdefault("name", name)
        mcp_names = cfg.get("mcp_list") or []
        if not isinstance(mcp_names, list) or any(not isinstance(x, str) for x in mcp_names):
            raise ProfileError(f"Agent {name}: mcp_list must be a list of server names")
        for tool in mcp_names:
            if tool not in servers:
                raise ProfileError(f"Agent {name}: MCP server {tool!r} is not defined")
        if cfg.get("reasoning") and not (cfg.get("reasoning_model") or cfg.get("reasoning_agent")):
            raise ProfileError(
                f"Agent {name}: Agno 3 requires an explicit reasoning_model or reasoning_agent"
            )
        if cfg.get("reasoning_agent") and cfg["reasoning_agent"] not in agents:
            raise ProfileError(f"Agent {name}: reasoning_agent must reference an agent in this profile")
        skills = cfg.get("skill_list") or []
        if isinstance(skills, str):
            skills = [skills]
        if not isinstance(skills, list) or any(not isinstance(p, str) for p in skills):
            raise ProfileError(f"Agent {name}: skill_list must contain paths")
        for path in skills:
            if not profile.path(path).is_dir():
                raise ProfileError(f"Agent {name}: skill directory does not exist: {path}")
        cfg["skill_list"] = skills
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name):
        if name in visiting:
            raise ProfileError("reasoning_agent references contain a cycle")
        if name in visited:
            return
        visiting.add(name)
        if agents[name].get("reasoning_agent"):
            visit(agents[name]["reasoning_agent"])
        visiting.remove(name)
        visited.add(name)

    for name in agents:
        visit(name)
