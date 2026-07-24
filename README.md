# rundeck-nexus-extension

Connect Rundeck diagnostic runbooks to incident.io Investigations via Nexus,
so an investigation can run read-only diagnostics and use the output as
evidence.

**Read [docs/DESIGN.md](docs/DESIGN.md) first** — it covers the plugin-vs-MCP
decision (answer: both, coupled), the data return path, and the safety model.

## What's in here

| Path | What |
|---|---|
| `docs/DESIGN.md` | The design: architecture, decision rationale, safety model, rollout phases |
| `gateway/` | Diagnostics Gateway — FastMCP server (Streamable HTTP + bearer token) exposing only `diagnostic`-tagged Rundeck jobs: `list_diagnostics`, `run_diagnostic`, `get_diagnostic_result` |
| `plugin/` | Nexus plugin (Anthropic plugin format) with the `rundeck-diagnostics` skill — teaches Investigations when/how to use the gateway |
| `rundeck/jobs/diagnostics/` | Sample diagnostic job definitions (YAML) following the conventions in the design doc |
| `docker-compose.yml` | Runs the gateway alongside the local Rundeck test instance |

## Quickstart (local test instance)

Assumes the local Rundeck from `/Users/chris/Rundeck` is up on
http://localhost:4440.

1. **Seed the diagnostic jobs.** Create a project (e.g. `diagnostics-demo`),
   then import each YAML in `rundeck/jobs/diagnostics/` (Jobs → Job Actions →
   Upload Definition, format YAML). Jobs land in the `diagnostics/` group
   tagged `diagnostic`.

2. **Create a least-privilege API token.** For the local test the admin token
   works; the real deployment uses a `nexus-gateway` user whose ACL grants
   `read` + `run` on the `diagnostics/` group only.

3. **Run the gateway:**

   ```bash
   cd /Users/chris/rundeck-nexus-extension
   RUNDECK_API_TOKEN=<rundeck token> \
   RUNDECK_PROJECT=diagnostics-demo \
   GATEWAY_BEARER_TOKEN=$(openssl rand -hex 24) \
   docker compose up -d --build
   ```

   MCP endpoint: `http://localhost:8710/mcp`

4. **Expose it to incident.io.** Localhost isn't reachable from Nexus, so
   either route through the incident.io **connector proxy** (pick your
   connector under "Private network" — matches the Connect MCP server
   screen) or tunnel it for a quick test (e.g. `ngrok http 8710`) and use
   "Public internet".

5. **Attach in Nexus** (Connect MCP server):
   - **Name:** `Rundeck Diagnostics`
   - **Server URL:** the gateway endpoint, ending `/mcp`
   - **Bearer token:** the `GATEWAY_BEARER_TOKEN` value
   - **Additional context:** something like:
     > Read-only diagnostic runbooks for our infrastructure. Call
     > list_diagnostics to discover checks. Safe to run during any
     > investigation; always cite the execution permalink when using output
     > as evidence. Project: diagnostics-demo.
   - Allowlist all three tools (the gateway exposes nothing dangerous).

6. **Load the plugin** (`plugin/`) into Nexus once plugin upload is available
   in your environment — the skill materially improves *when* and *how* the
   agent reaches for Rundeck. Until then, the "Additional context" field
   carries a compressed version of the same guidance.

7. **Test:** fire a test alert/incident, start an investigation, and check
   whether it calls `run_diagnostic` — or ask the agent directly: *"Run the
   service-health diagnostic for payments-api and interpret the result."*

## Phase 1 shortcut

For the very first end-to-end check you can attach the general-purpose
[justynroberts Rundeck MCP server](https://github.com/justynroberts/rundeck-mcp-server)
directly instead of the gateway (it needs to be fronted with HTTP transport +
a bearer token). Allowlist only `list_jobs`, `get_job`, `run_job`,
`get_execution`, `get_execution_output`. Understand the tradeoff: `run_job`
can run *any* job the token can see — fine on a demo box, not the shape to
put in front of a customer. That shape is the gateway.
