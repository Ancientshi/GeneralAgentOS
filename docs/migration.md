# Upgrade from the original script folder

Keep the old directory and environment until the new deployment has been verified. The public release
does not include personal agent profiles, MCP executables, credentials or databases.

1. Install this release in its own environment.
2. Move private MCP definitions from `config.py` into a local YAML mapping. Replace secrets with
   `${VARIABLE}` references and put their values in `.env`. Do not import/execute `config.py`.
3. Convert each agent's YAML overlays:

```bash
gaos import-legacy -c old/main.yaml -c old/NoReasoning.yaml -c old/SessionHistory.yaml \
  --mcp-registry private-mcp.yaml --base-url http://127.0.0.1:8000/v1 \
  --name my-agent --output profiles.local/profile.yaml
gaos validate -p profiles.local/profile.yaml
```

Review paths: all relative paths now resolve against the first profile. Old configurations that used
current-working-directory-relative paths must be adjusted. Replace removed `reasoning: true` with
an explicit `reasoning_model` or `reasoning_agent`. Model aliases no longer imply hidden endpoints.
Legacy custom evaluation scripts require separate migration; they are never silently run by this CLI.

4. Migrate a **new SQLite copy**, leaving the original untouched:

```bash
gaos migrate-db old/agent.db --session-table MyAgentSessions --output profiles.local/data/agent-v3.db
```

The command uses SQLite's backup API to take a consistent snapshot, runs Agno's official migration,
and checks every legacy session/run identity. It retains legacy run columns. It refuses to overwrite
an existing output. A failed migration leaves the source untouched; inspect the copy before using it.
For a final production cutover, stop old writers before taking the final snapshot so new conversations
are not lost. Do not point an old runtime at a migrated database.

5. Point the new profile at the migrated copy, choose an unused port and test it:

```bash
gaos deploy -p profiles.local/profile.yaml --name my-agent-v3
```

Only switch production traffic after validating model runs, MCP tools and history. Keep the old
deployment and database for rollback. Database-copy migration does not transfer conversations
written to the old service after the snapshot.

Upstream: [Agno v3 migration guide](https://docs.agno.com/other/v3-migration).
