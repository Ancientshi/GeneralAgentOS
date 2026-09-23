from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from . import AGNO_VERSION, __version__
from .profile import ProfileError, deep_merge, load_profile

TEMPLATE = """schema_version: 1
os:
  id: my-agent-os
  host: 127.0.0.1
  port: 7777
agents:
  assistant:
    model: gpt-4.1-mini
    provider: openai
    api_key_env: OPENAI_API_KEY
    instructions: |
      Help the user complete their task. Be concise and say when you are uncertain.
    storage_db: data/assistant.db
    add_history_to_context: true
    num_history_runs: 5
    mcp_list: []
    skill_list: []
mcp_servers: {}
"""


def parser():
    root = argparse.ArgumentParser(prog="gaos", description="Write a profile. Deploy an AgentOS.")
    root.add_argument(
        "--version", action="version", version=f"GeneralAgentOS {__version__} / Agno {AGNO_VERSION}"
    )
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create a starter profile and environment template")
    init.add_argument("directory", nargs="?", default="my-agent")
    for name, help_text in [
        ("validate", "Validate profile composition without model calls"),
        ("serve", "Run AgentOS in the foreground"),
        ("deploy", "Start a detached local deployment with health verification"),
    ]:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("-p", "--profile", action="append", required=True)
        cmd.add_argument("--env-file")
        if name == "deploy":
            cmd.add_argument("--name", default="my-agent")
    for name in ("status", "stop", "logs"):
        sub.add_parser(name).add_argument("name", nargs="?", default="my-agent")
    migration = sub.add_parser("migrate-db", help="Migrate and verify a new SQLite copy")
    migration.add_argument("source")
    migration.add_argument("--output", required=True)
    migration.add_argument("--session-table", default="agno_sessions")
    legacy = sub.add_parser("import-legacy", help="Convert composed legacy agent YAML into a v1 profile")
    legacy.add_argument("-c", "--config", action="append", required=True)
    legacy.add_argument("--output", required=True)
    legacy.add_argument("--name", default="assistant")
    legacy.add_argument("--base-url")
    legacy.add_argument("--mcp-registry", help="YAML mapping of MCP names to connection configurations")
    return root


def init_project(directory):
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    profile_path = path / "profile.yaml"
    if profile_path.exists() or (path / ".env").exists():
        raise ProfileError("Profile or .env already exists; choose a new directory")
    profile_path.write_text(TEMPLATE)
    fd = os.open(path / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as env:
        env.write("OPENAI_API_KEY=\nMODEL_API_KEY=\nGAOS_API_KEY=" + secrets.token_urlsafe(32) + "\n")
    ignore = path / ".gitignore"
    if not ignore.exists():
        ignore.write_text(".env\ndata/\n*.db*\n")
    print(f"Created {profile_path}. Set OPENAI_API_KEY in {path / '.env'}, then:")
    print(f"gaos deploy --profile {profile_path} --name {path.name}")


def import_legacy(args):
    output = Path(args.output)
    if output.exists():
        raise ProfileError("Output already exists")
    cfg = {}
    for file in args.config:
        part = yaml.safe_load(Path(file).read_text()) or {}
        if not isinstance(part, dict):
            raise ProfileError("Legacy configuration must be a mapping")
        deep_merge(cfg, part)
    port = cfg.pop("port", 7777)
    for key in ("reasoning", "reasoning_min_steps", "reasoning_max_steps"):
        if (
            key == "reasoning"
            and cfg.get(key)
            and not (cfg.get("reasoning_model") or cfg.get("reasoning_agent"))
        ):
            raise ProfileError("Choose an explicit reasoning model before migrating reasoning=true")
        cfg.pop(key, None)
    if cfg.pop("evaluation", False):
        raise ProfileError("Legacy evaluation mode requires manual migration to Agno evals")
    if cfg.get("knowledge_list"):
        raise ProfileError("Migrate knowledge_list to an explicit portable knowledge configuration")
    cfg.pop("knowledge_list", None)
    if "api_key" in cfg:
        raise ProfileError("Remove the embedded api_key; use api_key_env")
    if args.base_url:
        cfg["base_url"] = args.base_url
    cfg.setdefault(
        "api_key_env",
        "OPENAI_API_KEY" if cfg.get("provider", "openai").lower() == "openai" else "MODEL_API_KEY",
    )
    registry = yaml.safe_load(Path(args.mcp_registry).read_text()) if args.mcp_registry else {}
    data = {
        "schema_version": 1,
        "os": {"port": port, "host": "127.0.0.1"},
        "agents": {args.name: cfg},
        "mcp_servers": registry or {},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    print(f"Created {output}. Paths are relative to its directory; run gaos validate before serving.")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            init_project(args.directory)
        elif args.command == "import-legacy":
            import_legacy(args)
        elif args.command == "migrate-db":
            from .migrate import migrate_database

            print(json.dumps(migrate_database(args.source, args.output, args.session_table), indent=2))
        elif args.command in {"status", "stop", "logs"}:
            from .deploy import state_dir, status, stop

            if args.command == "logs":
                path = state_dir(args.name) / "server.log"
                print(path.read_text()[-20000:] if path.exists() else "No logs yet.")
            else:
                print(json.dumps((status if args.command == "status" else stop)(args.name), indent=2))
        else:
            env_path = (
                Path(args.env_file) if args.env_file else Path(args.profile[0]).resolve().parent / ".env"
            )
            if args.env_file and not env_path.is_file():
                raise ProfileError("The specified environment file does not exist")
            load_dotenv(env_path, override=False)
            profile = load_profile(args.profile)
            if args.command == "validate":
                print(f"Valid profile: {len(profile.data['agents'])} agent(s), Agno {AGNO_VERSION}")
            elif args.command == "deploy":
                from .deploy import deploy

                print(
                    json.dumps(
                        deploy(profile, args.name, str(env_path) if env_path.exists() else None), indent=2
                    )
                )
            else:
                import uvicorn

                from .runtime import create_app

                uvicorn.run(
                    create_app(profile),
                    host=profile.data["os"].get("host", "127.0.0.1"),
                    port=profile.data["os"]["port"],
                )
    except (ProfileError, FileNotFoundError, yaml.YAMLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return_code = 2
        raise SystemExit(return_code) from None
