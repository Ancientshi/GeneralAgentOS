# Changelog

## 1.0.2 — 2026-09-23

- Prefer compatible prebuilt dependencies in the installer, avoiding unnecessary compiler requirements on Intel macOS / Python 3.10.

## 1.0.1 — 2026-09-23

- Normalize double-encoded legacy session JSON on a private migration staging copy.
- Verify every legacy run field and publish the destination database only after validation succeeds.
- Add regression coverage for real legacy encoding and failed migrations.

## 1.0.0 — 2026-09-23

- Upgrade the runtime to Agno / AgentOS 3.0.10.
- Replace machine-specific Python configuration with composable YAML profiles and environment variables.
- Add init, validate, serve, deploy, status, logs, stop, import-legacy and migrate-db commands.
- Support OpenAI-compatible backends, multiple agents, explicit reasoning, local skills and MCP transports.
- Preserve session history with copy-first, verified SQLite migration and no legacy-column cleanup.
- Package a Python wheel, source distribution, one-command installer, Docker deployment and release CI.
- Remove embedded credentials, private server paths and runtime databases from the distributable.

### Migration notes

Legacy evaluation scripts and private model-provider subclasses are not packaged. Provider endpoints
are configured explicitly. Migrate evaluation code to the current Agno eval API separately.
`reasoning: true` now requires an explicit reasoning model/agent. New deployments default to localhost.
