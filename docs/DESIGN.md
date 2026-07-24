# Design: Rundeck diagnostics for incident.io Investigations (Nexus)

**Status:** Draft v1 — 2026-07-24
**Author:** Chris Bell
**Goal:** Let Investigations AI call diagnostic runbooks in Rundeck during an
investigation and feed the results back as evidence.

---

## 1. The decision: plugin or MCP?

**Both — they solve different halves of the problem and Nexus is built to couple them.**

Nexus extensibility has two primitives under the "Extensions" umbrella:

| Primitive | What it gives you | What it can't do |
|---|---|---|
| **MCP connector** | *Reach* — network connectivity into your systems. Tools are auto-discovered, allowlisted per-tool, callable by Investigations and agents. | Doesn't teach the agent *when* to call a tool, *which* job maps to *which* symptom, or how to interpret output. That knowledge lives only in tool descriptions. |
| **Plugin** (Anthropic plugin format: skills + runbooks + files) | *Knowledge and packaging* — skills that tell the agent when to reach for Rundeck, how to map incident context to job options, safety rules, how to read results. Runbooks you want run *reliably* belong in the plugin package. | No connectivity. A skill can't touch Rundeck without a connector to call. |

The failure modes of picking only one:

- **MCP only:** the agent sees `run_job` among dozens of tools and has to guess
  from a one-line description whether "disk-usage-check" is relevant to a p99
  latency alert. Tool selection quality is the known weak point — this is
  exactly what the extensions team observed with MCP-wrapped telemetry
  ("putting that behind an MCP loses all those optimisations").
- **Plugin only:** the skill can describe the diagnostic procedure beautifully
  but has no way to execute it.

So: **the MCP connector is the hands, the plugin skill is the operating manual.**

## 2. Architecture

```
┌────────────────────────── incident.io ──────────────────────────┐
│  Investigation / Agent (Nexus)                                   │
│   ├─ Plugin: rundeck-diagnostics skill                           │
│   │    "when you see symptom X, run diagnostic Y with options Z" │
│   └─ MCP connector: Rundeck Diagnostics Gateway                  │
│        tools: list_diagnostics, run_diagnostic,                  │
│               get_diagnostic_result                              │
└───────────────┬──────────────────────────────────────────────────┘
                │ Streamable HTTP + bearer token
                │ (public URL, or private network via connector proxy)
                ▼
┌── Diagnostics Gateway (this repo, FastMCP) ─────────────────────┐
│  • exposes ONLY jobs tagged `diagnostic`                         │
│  • runs job, waits (bounded), returns structured output          │
│  • truncates logs to a tail the LLM can use                      │
└───────────────┬──────────────────────────────────────────────────┘
                │ Rundeck API token (least-privilege ACL)
                ▼
        Rundeck (jobs in diagnostics/ group, tagged `diagnostic`)
```

### Why a purpose-built gateway instead of attaching the general Rundeck MCP server directly?

The justynroberts server is great for interactive use (Claude Desktop/Code, a
human in the loop confirming `run_job`). For an *autonomous* investigation
agent it has three mismatches:

1. **Blast radius.** `run_job` can execute *any* job the API token can see.
   Nexus's per-tool allowlist operates at tool granularity, not job
   granularity — allowing `run_job` allows every job. Guardrails must be
   server-side, not prompt-side.
2. **Confirmation flow.** Its two-step `confirmed=True` dance is designed for
   a human; an agent will just pass `confirmed=True`, so the ceremony adds
   tokens without adding safety.
3. **Data return shape.** Investigations evidence works best as one
   synchronous tool result. The general server returns an execution id and
   expects offset-based log polling — fine for a human tailing output, noisy
   for an agent mid-investigation.

The gateway is ~200 lines and enforces: job must carry the `diagnostic` tag,
execution is awaited up to a bounded timeout, output is returned as a
structured summary (status, duration, tail of logs, link back to Rundeck).

**Phase 1 shortcut:** for the first end-to-end test you can attach the
justynroberts server directly (allowlist the read tools + `run_job`, put
steering text in the connection's "Additional context" field). The gateway is
the shape you'd actually ship to a customer.

## 3. How data gets back into the investigation

Three paths, in order of preference:

1. **Synchronous tool result (primary).** `run_diagnostic` blocks until the
   job completes (default ≤120s) and returns `{status, duration,
   exit_summary, log_tail, permalink}`. The result lands directly in the
   investigation's context as evidence — no extra plumbing. This is how MCP
   telemetry sources already feed Investigations.
2. **Poll for long runners.** If the job outlives the wait budget,
   `run_diagnostic` returns `{status: "running", execution_id, permalink}` and
   the skill instructs the agent to call `get_diagnostic_result(execution_id)`
   before concluding. The agent's own loop is the scheduler.
3. **Push (optional, later).** Rundeck job notification → webhook →
   incident.io alert event / API, attaching output to the incident timeline.
   Useful for human-triggered runbooks whose results should appear in the
   incident even when no agent asked; *not* needed for the investigation loop,
   which is pull-based.

Output discipline matters more than transport: diagnostic jobs should print a
**final structured summary block** (see job conventions below) so the tail
truncation never cuts the conclusion.

## 4. Safety model

- **Diagnostics are read-only by convention and by ACL.** The gateway's
  Rundeck API token belongs to a `nexus-gateway` user whose ACL grants `read`
  + `run` on the `diagnostics/` job group only — nothing else. Tag filtering
  is a convenience; the ACL is the boundary.
- **No remediation in v1.** Investigations only ever needs to *read* state.
  Remediation (restart service, scale up) stays human-triggered. When we do
  want agent-proposed remediation, it goes through a separate gateway tool
  with incident.io-side approval, never silently.
- **Bearer token on the gateway** (checked on every request), rotated like any
  service credential. For private networks, route via the incident.io
  connector proxy instead of exposing the endpoint publicly.
- **Least surprising failure:** unknown job, missing required option, or
  non-diagnostic job → explicit tool error the agent can read, not a stack
  trace.

## 5. Rundeck job conventions (what makes a job "diagnostic")

- Lives in the `diagnostics/` group and carries the `diagnostic` tag.
- Description states *when to run it* and *what it returns* — the gateway
  passes descriptions through to the agent, so write them for an LLM reader.
- Options are named plainly (`service`, `host`, `window_minutes`) with
  sensible defaults; enforced allowed-values where possible.
- Idempotent, side-effect-free, bounded runtime (target <60s).
- Ends by printing a summary block:

  ```
  === DIAGNOSTIC SUMMARY ===
  result: unhealthy
  detail: payments-api p99 4.2s (threshold 1s); 3/10 pods CrashLoopBackOff
  ```

## 6. The plugin

Anthropic plugin format (same scaffolding incident.io injects into Cowork —
confirmed natively supported by Nexus). One skill to start:

- `skills/rundeck-diagnostics/SKILL.md` — when to use Rundeck during an
  investigation, the tool call sequence, option-mapping guidance, output
  interpretation, and hard safety rules (never treat a diagnostic as a fix;
  report execution permalinks as evidence).

Later: bundle runbook markdown for procedures that *aren't* codified in
Rundeck yet (the Confluence-runbook reality), so one plugin carries both
"run this job" and "follow this procedure" knowledge.

## 7. Rollout phases

| Phase | What | Proves |
|---|---|---|
| 1 | Attach justynroberts MCP directly to Nexus (test env), tool allowlist + additional-context steering. Seed `diagnostics/` jobs. | End-to-end: investigation calls a Rundeck job, result appears as evidence. |
| 2 | Deploy this gateway + plugin skill. Compare tool-selection quality vs phase 1. | The productisable shape: job-level guardrails, structured returns, skill-guided selection. |
| 3 | Demo narrative: incident fires → investigation runs `service-health` + `recent-logs` → cites output in findings. Loom it. | The "we plug into your existing automation" story vs PD's SRE agent. |

## 8. Why this matters commercially

This is the **MCP as Automation Bridge** play: incident.io doesn't compete
with the customer's automation stack (Rundeck, Ansible, SSM) — it makes that
stack smarter with real incident context. PagerDuty's chain is Event
Orchestration → Automation Actions → Rundeck, three systems with silent
failure modes and ~5% practical coverage. Our story: one skill + one
connector, and the AI decides *which* diagnostic is relevant using the full
incident context. Rundeck OSS makes this demoable in an afternoon.
