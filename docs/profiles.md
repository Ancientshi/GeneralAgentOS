# Profile reference

`schema_version: 1` contains `os`, `agents` (a nonempty name-to-configuration mapping), and optional
`mcp_servers`. YAML overlays recursively merge maps and replace lists. Relative paths are anchored
to the first profile; environment values are resolved after merging. `.env` beside the first profile
loads automatically without overriding the shell environment; `--env-file` selects another file.

`os`: `id`, `name`, `description`, `host` (127.0.0.1), `port` (7777), `cors_origins` (list),
`api_key_env` (GAOS_API_KEY), `authorization` (false), `jwt_verification_key_file` (optional).
A non-loopback host requires an API key or configured JWT authorization.

For the Agno Control Plane's Token-Based Authorization (JWT), enable the switch in the
Control Plane, save its public verification key as a PEM file, and add an overlay:

```yaml
os:
  authorization: true
  jwt_verification_key_file: /etc/general-agent-os/control-plane-public.pem
  cors_origins:
    - https://os.agno.com
```

This uses Agno's native RS256 signature validation and scope authorization. Relative key
paths follow the first profile's directory. Alternatively, omit the file setting and set
Agno's `JWT_VERIFICATION_KEY` or `JWT_JWKS_FILE` environment variable. A missing verification
source prevents startup. Do not supply a private signing key.

JWT mode does not install the legacy `GAOS_API_KEY` middleware, which would otherwise reject
Control Plane tokens before Agno can validate them. Static API keys cannot authenticate on a
JWT endpoint. To retain an existing static-key client, run a separate instance with the
original profile and use a JWT overlay on a different port for the Control Plane.

Each agent requires `model`. Use `provider: openai` (default) or `openai-compatible`, `vllm`,
`proxyllm`, `siliconflow`, `jacobapi`. Non-OpenAI providers require `base_url`. These names all use
Agno's OpenAI Chat transport; they do not bundle private endpoints or keys. `api_key_env` defaults
to OPENAI_API_KEY for OpenAI and MODEL_API_KEY otherwise. For local servers without authentication,
set the chosen variable to `EMPTY` explicitly.

`model_options` passes supported OpenAIChat options such as temperature/max_tokens.
`extra_body` and `request_params` are sent to the model, allowing vLLM-specific settings.

`storage_db` defaults to `data/<agent-name>.db`; `storage_table` defaults to `agno_sessions`.
`db_id` identifies the database in AgentOS. Give separate agents distinct database files unless
you explicitly intend shared storage. In Docker, use `${GAOS_DATA_DIR:-data}/my-agent.db`.

`skill_list` accepts directories containing Agno skills. Directories must exist during validation.
`mcp_list` references server names. `include_tools`, `exclude_tools`, `timeout_seconds` and
`tool_call_limit` control tool access and invocation. Server definitions accept:

```yaml
mcp_servers:
  local:
    command: python
    args: [server.py]
    cwd: ./tools
    env:
      TOOL_API_KEY: ${TOOL_API_KEY}
  remote:
    url: https://your-server.example/mcp
    transport: streamable-http # or sse
    headers:
      Authorization: Bearer ${TOOL_TOKEN}
    tool_name_prefix: remote
```

Stdio programs are trusted local code executed with the server's environment. Inspect a profile
before running it. AgentOS owns MCP connection and shutdown lifecycle; startup fails if a required
server cannot connect. No MCP process is launched by `gaos validate`.

`reasoning_model` accepts a model ID (same provider/options as the main model) or a complete model
mapping. `reasoning_agent` names another agent in the same profile. Cycles are rejected.
Deprecated `reasoning: false` and min/max-step fields are tolerated when importing old profiles;
step limits no longer apply to Agno 3's native reasoning models.

Other supported Agno Agent constructor options (e.g. `instructions`, `description`, `markdown`,
`add_history_to_context`, `num_history_runs`, `read_chat_history`, `debug_mode`) pass through.
Object-valued `tools`, `skills` and `db` cannot be supplied as raw YAML. Unknown options fail fast.

Optional `knowledge` uses Chroma and requires `.[knowledge]`:

```yaml
knowledge:
  path: ./data/knowledge
  collection: documents
  embedder: text-embedding-3-small
```

This attaches an existing collection; ingest content with Agno's Knowledge API before querying it.
