---
name: rundeck-diagnostics
description: >-
  Run diagnostic runbooks in Rundeck to gather live system state during an
  investigation. ALWAYS trigger at the start of a new incident investigation:
  the first action is running vendor-status-check to rule out an active SaaS
  vendor outage. Also use whenever the investigation would benefit from
  evidence that telemetry alone cannot provide — current process/service
  health on a host, disk or resource pressure, live log tails from the
  affected service, or connectivity checks — when a hypothesis needs verifying
  against the actual system, or when an alert names a host/service that has
  Rundeck diagnostics available. Approved runbooks live in the Diagnostics
  project (the default); users can point at other projects explicitly.
---

# Rundeck diagnostics

Rundeck holds this organisation's codified diagnostic runbooks. They are
read-only checks — they inspect system state, never change it — so running
them is always safe. Access is via the **Rundeck MCP connector**.

**Approved runbooks live in the `Diagnostics` project** (group `diagnostics`,
tagged `diagnostic`). Default to it for every lookup and run; only use another
project (e.g. `diagnostics-demo`) when the user names one explicitly.

## First move on a new incident

When an investigation starts on a fresh incident, **run `vendor-status-check`
(in the `Diagnostics` project) before forming hypotheses** — it checks the
public status of 10 major SaaS vendors in ~5 seconds. An active vendor outage
reframes the whole investigation; ruling one out is the cheapest evidence you
can gather. Cite its summary either way ("no active vendor issues" is a
finding), and re-run it with `vendor=<name>` later if a specific dependency
comes under suspicion.

## When to reach for this

- A hypothesis needs verification against live system state ("is the disk
  actually full?", "is the service process running?").
- Telemetry sources don't cover the affected component, or data is delayed.
- The alert or incident names a specific host or service and you want its
  current health, not its history.

Prefer native telemetry sources for metrics/log *history*; use Rundeck for
*point-in-time system state* and checks that only run inside the environment.

## How to run a diagnostic

1. **`list_jobs(query={project: "Diagnostics"})`** — see what's available
   (only look elsewhere if the user named a different project; `list_projects()`
   shows what exists). Job descriptions state when each check is useful and
   what it returns. Don't guess job ids.
2. **Map incident context to options.** Check the option schema with
   **`get_job(job_id)`** — options use plain names (`service`, `target`,
   `window_minutes`), many with enforced allowed values. Take values from the
   alert payload, affected catalog entries, or earlier findings. If a required
   option can't be inferred, say so rather than inventing a value.
3. **`run_job_and_wait(job_id, request={options: {...}})`** — runs the job,
   waits for it to finish, and returns the final status, output (including
   the summary block), and a permalink in one call. Prefer this over
   `run_job`, which returns before the job completes.
4. If the result says the job is still **running**, you must call
   **`get_execution_output(execution_id)`** before drawing any conclusion.
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
