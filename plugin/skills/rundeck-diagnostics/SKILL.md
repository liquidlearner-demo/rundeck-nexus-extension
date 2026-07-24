---
name: rundeck-diagnostics
description: >-
  Run diagnostic runbooks in Rundeck to gather live system state during an
  investigation. Use whenever the investigation would benefit from evidence
  that telemetry alone cannot provide — current process/service health on a
  host, disk or resource pressure, live log tails from the affected service,
  or connectivity checks. Trigger when a hypothesis needs verifying against
  the actual system, when telemetry is stale or missing for the affected
  component, or when an alert names a host/service that has Rundeck
  diagnostics available.
---

# Rundeck diagnostics

Rundeck holds this organisation's codified diagnostic runbooks. They are
read-only checks — they inspect system state, never change it — so running
them is always safe. Access is via the **Rundeck Diagnostics Gateway** MCP
connector, which only exposes diagnostic jobs.

## When to reach for this

- A hypothesis needs verification against live system state ("is the disk
  actually full?", "is the service process running?").
- Telemetry sources don't cover the affected component, or data is delayed.
- The alert or incident names a specific host or service and you want its
  current health, not its history.

Prefer native telemetry sources for metrics/log *history*; use Rundeck for
*point-in-time system state* and checks that only run inside the environment.

## How to run a diagnostic

1. **`list_diagnostics()`** — see what's available. Job descriptions state
   when each check is useful and what it returns. Don't guess job ids.
2. **Map incident context to options.** Job options use plain names
   (`service`, `host`, `window_minutes`). Take values from the alert payload,
   affected catalog entries, or earlier findings. If a required option can't
   be inferred, say so rather than inventing a value.
3. **`run_diagnostic(job_id, options)`** — runs the job and returns status,
   output tail, and a permalink. Most diagnostics finish inside the call.
4. If the result says the job is still **running**, you must call
   **`get_diagnostic_result(execution_id)`** before drawing any conclusion.
   Never cite an in-flight or timed-out run as evidence.

## Reading the output

- Each job ends with a `=== DIAGNOSTIC SUMMARY ===` block — that is the
  authoritative conclusion; the lines above it are supporting detail.
- A **failed** execution usually means the check itself could not run
  (missing host, bad option), not that the system is unhealthy. Treat it as
  "no evidence", report why, and consider a different diagnostic — don't
  fold a failed run into your hypothesis either way.
- Always include the execution permalink when citing a diagnostic in
  findings, so responders can see the full output.

## Hard rules

- Diagnostics gather evidence. They are **never** a fix, and their success
  does not mean the incident is resolved.
- Do not retry a diagnostic more than twice; repeated failure is a finding
  in itself ("could not verify X because the disk-usage check errors").
- If no available diagnostic fits, say so explicitly rather than running a
  loosely related one and over-interpreting its output.
