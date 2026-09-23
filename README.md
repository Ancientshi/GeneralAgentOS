# General Agent OS

**Write an agent profile. Deploy it in one command.**

General Agent OS turns portable YAML profiles into [Agno AgentOS](https://docs.agno.com/agent-os/overview)
services. Define the model, instructions, MCP tools, skills and conversation history without writing
application code. Start one agent or several through the same API.

[中文文档](README.zh-CN.md) · [Profile reference](docs/profiles.md) · [Upgrade guide](docs/migration.md)

## Install

Linux, Python 3.10 or newer:

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
Bind to a non-loopback address only with a configured API key or JWT authorization; use HTTPS at
your reverse proxy. The default shared key grants full access and does not provide per-user
isolation. For the Agno Control Plane, use its **Token-Based Authorization (JWT)** switch and a
public verification key; this is a different mode from the shared `GAOS_API_KEY`. See the
[profile reference](docs/profiles.md) for the overlay and for running both modes on separate ports.

## Optional benchmark skills

[Benchmark Lab](extensions/benchmarks/README.md) is an independently installed skill and MCP extension
for choosing data-science benchmark tasks, collecting artifacts and routing submissions to upstream
evaluators. It includes adapters for DARE-Bench, CoDA-Bench, DDR-Bench, DAComp and both Ambig-DS suites,
with explicit setup requirements and an extension contract for additional suites. It uses existing
profile fields and does not add benchmark dependencies to the core runtime.

[Data Science Lab](extensions/data-science/README.md) adds 24 resource cards, six focused analysis skills
and ten portable model/analysis recipes. Its independent MCP service supplies method discovery and code
templates; the benchmark sandbox executes them and the official evaluator scores the artifacts.
The combined profile is `extensions/data-science/profile.yaml`. Optional Hugging Face and Kaggle metadata
search is separate from the default offline benchmark workflow. See the extension's validation table
for tested baseline recipes versus optional model templates.

## Verification and current limits

The following is the **2026-09-23 deployment check**, not a claim that every benchmark or model
has been fully evaluated:

| Check | Observed result and scope |
|---|---|
| Code | 29 targeted authorization/profile/runtime tests and 20 benchmark-engine tests passed; Ruff passed. This is not a full five-benchmark experiment. |
| Live AgentOS | The API, Agent UI, Agno Control Plane JWT endpoint and rootless execution sandbox ran on the cloud server. The Control Plane connection opened after the server clock was corrected; the user confirmed Chat opened. |
| Model connectivity | The deployed agent uses an OpenAI-compatible local Proxy LLM, `gpt-6-luna`, through an SSH reverse tunnel. A live AgentOS chat called a benchmark tool and completed. This checks connectivity and tool use, not autonomous benchmark solving. The laptop's proxy and tunnel must remain online for chat. |
| Official evaluation | One DARE-Bench Pokemon Unite classification task (`v2`, 66 training rows and 8 prediction rows) was scored by the upstream evaluator: majority baseline macro F1 `0.181818`; a run supplied with RandomForest solution code scored `0.629630`. That score validates execution, submission and evaluator routing; it is **not** an autonomous agent score. |
| Autonomous solving | A separate attempt with the earlier Qwen3-8B deployment produced no valid submission or official score. `gpt-6-luna` has not yet completed an autonomous benchmark run. |

Only that DARE task's data is installed on the example server. The other benchmark adapters and
DARE task index are available, but their task data, evaluator dependencies or judge access must
be prepared separately. Of Data Science Lab's ten recipes, seven CPU recipes were run on synthetic
data; the three optional model recipes were checked for interface/compilation but their heavyweight
dependencies and weights are not installed on that server. See the [benchmark setup and protocol
limits](extensions/benchmarks/README.md) and [recipe validation](extensions/data-science/README.md).

The live model choice is deployment configuration, not a repository default. To use the same
OpenAI-compatible proxy in your own profile, set `provider: proxyllm`, `model: gpt-6-luna`,
`base_url: http://127.0.0.1:18080/v1` and an `api_key_env` appropriate for your proxy. The
verified proxy also required `model_options.reasoning_effort: none` for tool calls. On a remote
server, `127.0.0.1` means the server itself, so forward the local proxy to that address first.

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
