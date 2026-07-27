---
name: rundeck-job-authoring
description: >-
  Author new diagnostic runbooks in Rundeck — typically during a post-incident
  review (PIR) or when working a follow-up. Use when the team identifies a
  diagnostic they wish they'd had during the incident, when an investigation
  repeatedly ran the same manual check, or when someone asks to codify a
  runbook. Drafts a job definition from an existing template, proposes it for
  review, and creates it in Rundeck only after a human approves.
---

# Rundeck job authoring

Rundeck holds this organisation's codified diagnostic runbooks. During a PIR,
the most valuable follow-up is often "make the check we did by hand into a
runbook" — so the next investigation gets it in one call. This skill covers
authoring those jobs via the Rundeck MCP connector.

## When to reach for this

- A PIR identifies a diagnostic gap ("we spent 20 minutes checking X manually").
- An investigation ran the same ad-hoc check more than once.
- A follow-up action asks for new diagnostic coverage.

**Diagnostics only.** Never author remediation jobs — no restarts, deletes,
config changes, or anything that mutates system state. If asked for one,
decline and suggest a human-owned runbook instead.

## The workflow

1. **Find a template.** Check the **`_Templates` project first** — it holds a
   library of sample jobs grouped by category (diagnostics, container-management,
   database-management, storage-management, finops, automation), each marked
   TEMPLATE with execution disabled. `list_jobs(query={project: "_Templates"})`
   → pick the closest match → `get_job_definition(job_id)` for its full YAML.
   Live working examples are in `diagnostics-demo` (group `diagnostics`).
   Starting from a template beats writing from scratch.
2. **Draft the variant.** Edit the YAML: new kebab-case `name`, remove the
   `id`/`uuid` fields (so a new job is created), adjust description, options,
   and script to the new check. Follow the conventions below.
3. **Propose, don't create.** Post the draft YAML in the PIR discussion or
   follow-up with a plain-English summary: what it checks, when to run it,
   what the summary block will say. **Only call `create_job` after a human
   approves — or when the request explicitly asks you to create it.**
4. **Create.** `create_job(project, job_yaml)`. To *update* an existing job
   instead, keep its `uuid` and pass `dupe_option="update"`. Note: Rundeck
   matches duplicates by uuid, not name — uuid-less YAML always creates a new
   job, so re-importing without a uuid produces same-named duplicates.
5. **Verify.** `run_job_and_wait(new_job_id, request={options})` must return
   `succeeded` with a well-formed summary block before you cite the job. If it
   fails, fix the YAML and re-import with the new job's uuid +
   `dupe_option="update"` — never leave a broken job behind.
6. **Report.** Include the job permalink and the verification execution
   permalink in the PIR or follow-up.

## House conventions for job YAML

The definition is a YAML **list** of job maps (one job per create_job call):

```yaml
- name: my-diagnostic            # kebab-case, verb-noun
  group: diagnostics
  description: >-
    What it checks, when an investigator should run it, and what it returns.
  tags: 'diagnostic'
  loglevel: INFO
  options:
    - name: service              # snake_case option names
      description: Which service to check.
      required: true
      value: gateway             # defaults are quoted strings
      enforced: true             # enforced + values for bounded choices
      values: [gateway, catalog-service, checkout-service, payments-service]
  sequence:
    keepgoing: false
    strategy: node-first
    commands:
      - script: |
          #!/bin/bash
          service="@option.service@"
          # ... read-only checks, finish in under 60 seconds ...
          echo "=== DIAGNOSTIC SUMMARY ==="
          echo "result: healthy"            # healthy | unhealthy | error
          echo "detail: one-line conclusion"
```

- The script must be **read-only** and finish in **under 60 seconds**.
- It must **end** with the `=== DIAGNOSTIC SUMMARY ===` block (`result:` is
  `healthy`, `unhealthy`, or `error` — where `error` means the check itself
  could not run). It goes last so output truncation never cuts the conclusion.
- Options are referenced in scripts as `@option.name@`.

## Hard rules

- **Propose before create.** Never call `create_job` without a human's
  go-ahead, unless the request explicitly asks you to create the job.
- **Diagnostics only.** Read-only scripts; refuse remediation jobs.
- Never use `dupe_option="update"` on a job you did not author in this
  session unless a human confirms the overwrite.
- Every created job must be verified with a successful run before you cite it.
- Always include permalinks (job + verification execution) when reporting.
