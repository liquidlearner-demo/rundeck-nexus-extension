---
name: awx-diagnostics
description: >-
  Run diagnostic playbooks on the Ansible automation backend (AWX) during an
  investigation. Use when the user or owning team mentions Ansible, AWX,
  playbooks, or job templates, or when the runbook you need lives in AWX
  rather than Rundeck. Gathers live system state that telemetry alone cannot
  provide, via parameterized Ansible job templates.
---

# AWX (Ansible) diagnostics

AWX runs this organisation's Ansible-based diagnostic runbooks. Playbooks live
in git (project `awx-demo-playbooks`) and are executed via **job templates** —
parameterized, read-only checks that inspect system state without changing it.
Access is via the **AWX MCP connector**, which exposes the same tools as the
Rundeck connector.

Backend routing: Rundeck's `Diagnostics` project is the default home for
incident-start diagnostics — including the vendor-status-check first move,
which belongs to the rundeck-diagnostics skill. **If vendor-status-check has
already run on either backend this incident, don't repeat it on the other.**
Reach for AWX when the check you need is Ansible-based or owned by an
Ansible-centric team.

## When to reach for this

- The needed runbook is an Ansible playbook / AWX job template.
- The affected service's team operates through Ansible ("run the playbook").
- A hypothesis needs verification against live system state and the AWX
  library has the fitting check.

Prefer native telemetry for metrics/log *history*; use automation backends for
*point-in-time system state*.

## How to run a diagnostic

1. **`list_jobs()`** — see the available job templates. Descriptions state
   when each check is useful. Don't guess job ids.
2. **Check the variable schema with `get_job(job_id)`** — options are Ansible
   variables (extra_vars), e.g. `vendor`, `service`, `target_host`, shown with
   defaults and any survey choices. Take values from the alert payload or
   earlier findings; if a required variable can't be inferred, say so rather
   than inventing a value.
3. **`run_job_and_wait(job_id, options={...})`** — launches the template with
   your options as extra_vars, waits for a terminal state, and returns the
   final status plus output in one call.
4. If still **running** after the wait budget, call
   **`get_execution_output(execution_id)`** before drawing any conclusion.
   Never cite an in-flight or timed-out run as evidence.

## Reading the output (Ansible nuances)

- The `=== DIAGNOSTIC SUMMARY ===` block is the authoritative conclusion. In
  AWX output it appears inside the report task's `msg` list — quoted lines
  like `"result: healthy"` — the quoting is Ansible formatting, not part of
  the verdict.
- Ansible's `PLAY RECAP failed=0` means the *check ran successfully*; the
  summary block states whether the *system* is healthy. Don't conflate them.
- A **failed** job usually means the check itself couldn't run (unreachable
  host, bad variable), not that the system is unhealthy. Treat it as "no
  evidence" and report why.
- Always include the AWX job permalink when citing a diagnostic in findings.

## Hard rules

- Diagnostics gather evidence. They are **never** a fix, and their success
  does not mean the incident is resolved.
- Do not retry a diagnostic more than twice; repeated failure is a finding.
- If no available template fits, say so explicitly rather than running a
  loosely related one and over-interpreting its output.
