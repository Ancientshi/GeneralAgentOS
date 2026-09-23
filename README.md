# General Agent OS

**Write an agent profile. Deploy it in one command.**

General Agent OS turns portable YAML profiles into [Agno AgentOS](https://docs.agno.com/agent-os/overview)
services. Define the model, instructions, MCP tools, skills and conversation history without writing
application code. Start one agent or several through the same API.

[中文文档](README.zh-CN.md) · [Profile reference](docs/profiles.md) · [Upgrade guide](docs/migration.md)

## Install

Linux / macOS, Python 3.10 or newer:

```bash
curl -fsSL https://raw.githubusercontent.com/Ancientshi/GeneralAgentOS/v1.0.2/install.sh | bash
```

The installer creates a dedicated environment under `~/.local/share/general-agent-os`, verifies the
release wheel against its SHA-256 manifest and installs `~/.local/bin/gaos`. It never needs sudo.
Add `~/.local/bin` to PATH if requested. You can also inspect the script before running it.

From a downloaded release/source checkout (also works before an online release exists):

```bash
bash install.sh
# Or use your own virtual environment:
python -m pip install '.[mcp]'
```

## Your first agent

```bash
gaos init my-agent
# Edit my-agent/.env: set OPENAI_API_KEY.
# Edit my-agent/profile.yaml: choose the model and write its instructions.
gaos validate -p my-agent/profile.yaml
gaos deploy -p my-agent/profile.yaml --name my-agent
gaos status my-agent
gaos logs my-agent
gaos stop my-agent
```

`init` generates a deployment API key in `.env`. Clients send it as `Authorization: Bearer …`.
`GET /health` is public. Open `http://127.0.0.1:7777/health` to check readiness.
The service uses Agno's standard `/agents`, `/agents/{agent_id}/runs` and session APIs.
Use `gaos serve -p my-agent/profile.yaml` for foreground development.

```yaml
schema_version: 1
os:
  port: 7777
agents:
  research-assistant:
    model: gpt-4.1-mini
    instructions: |
      Answer research questions clearly. Separate evidence from your interpretation.
    add_history_to_context: true
    num_history_runs: 5
    mcp_list: [research-tools]
mcp_servers:
  research-tools:
    url: https://your-mcp-server.example/mcp
    transport: streamable-http
```

Replace the example MCP address with your own service, or use `mcp_list: []` to start without tools.
Choose any model available from your provider; the example model is not a requirement.

## Profiles are the deployment unit

- Compose overrides: `gaos serve -p profile.yaml -p production.yaml`.
- Use any OpenAI-compatible service, including vLLM; set `provider`, `base_url`, and `api_key_env`.
- Attach MCP servers over stdio, SSE or streamable HTTP, with tool allow/deny lists.
- Load local Agno skills from `skill_list` paths.
- Add multiple agents and explicit reasoning models or reasoning-agent references.
- Keep per-agent SQLite session history. Existing databases can be migrated on verified copies.
- Detect misspelled fields, missing environment variables, duplicate IDs and reasoning cycles before serving.

Later profile files override scalars and lists and recursively merge mappings. All relative paths
are resolved from the **first** profile, so commands work from any working directory.
Environment values use `${NAME}` (required) or `${NAME:-default}`; credentials belong in `.env`.

## Docker deployment

```bash
cp .env.example .env
# Set OPENAI_API_KEY and a long random GAOS_API_KEY in .env.
docker compose up -d --build
curl http://127.0.0.1:7777/health
docker compose logs -f
```

Compose runs as a non-root user, persists SQLite data in a named volume, binds to localhost on the
host and restarts the service after a reboot. Put profiles/skills under `examples/` or change the
read-only `/profiles` mount. A stdio MCP server must have its executable and dependencies installed
inside the container; host-only MCP programs work with the native `gaos` deployment instead.

The local `gaos deploy` command detaches from the terminal and verifies startup. It does **not**
provide automatic restart after a crash or reboot; use Compose or your service manager for that.
Bind to a non-loopback address only with a configured `GAOS_API_KEY`; use HTTPS at your reverse proxy.
The shared key grants full access to this deployment. This release does not provide per-user isolation.

## Development and releases

```bash
python -m pip install '.[mcp,dev]'
pytest -q
ruff check src tests
python -m build
```

Release 1.0.2 pins **Agno 3.0.10**, verified against PyPI and the upstream stable release on
2026-09-23. This avoids unexpected major-version upgrades. See [CHANGELOG.md](CHANGELOG.md).
Tests exercise API startup, streamed and non-streamed model runs with a local fake backend,
MCP lifecycle, profile validation, detached deployment and database migration without paid API calls.

Pushing a `v*` tag runs CI, builds wheel/sdist/source archives and checksums, creates a GitHub Release,
and publishes `ghcr.io/ancientshi/generalagentos` images. See [release procedure](docs/releasing.md).

MIT licensed. Agno and other dependencies retain their own licenses. This is an independent project.
