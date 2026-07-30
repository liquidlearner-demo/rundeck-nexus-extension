---
name: awx-job-authoring
description: >-
  Author new diagnostic automation on the Ansible backend (AWX) — typically
  during a post-incident review or follow-up. Use when the runbook being
  codified belongs to an Ansible-centric team or should be an Ansible
  playbook, when someone asks to codify a check "as a playbook", or when a
  new job template is needed over an existing playbook. Proposes changes for
  review and creates only after a human approves.
---

# AWX (Ansible) job authoring

AWX has a **two-layer model** that shapes how authoring works:

- **Playbooks** hold the executable logic and live in git
  (`liquidlearner-demo/awx-demo-playbooks`). AWX syncs them from the repo.
- **Job templates** make a playbook runnable: they bind it to an inventory and
  expose its variables at launch.

So there are two authoring paths:

1. **New template over an existing playbook** — e.g. a preset-variable variant
   of an existing check. After proposing and getting approval, call
   `create_job(name, playbook, description)` directly.
2. **New playbook** — draft the playbook YAML (and script, per the conventions
   below) and **propose it as a git change** to the playbooks repo in the PIR
   discussion. A human reviews and merges; AWX's project sync picks it up;
   then `create_job` wires a template around it. **The agent never has git
   push access — the merge is the control point.**

## The workflow

1. **Find a template to copy.** `list_jobs()` → `get_job_definition(job_id)`
   shows an existing template's config and which playbook it runs, plus the
   git repo the playbook lives in. Start from the closest existing check.
2. **Draft.** Follow the repo conventions (below). Keep checks read-only and
   fast.
3. **Propose, don't create.** Post the draft (template config, and playbook
   YAML if new) in the PIR discussion with a plain-English summary. **Only
   proceed after a human approves — or when explicitly asked to create it.**
4. **Create.** For an existing playbook: `create_job(...)`. For a new
   playbook: wait until the git change is merged and the AWX project has
   synced, then `create_job(...)`.
5. **Verify.** `run_job_and_wait(new_template_id, options)` must return
   `succeeded` with a well-formed summary before you cite it. If it fails,
   fix and re-propose — never leave a broken template behind.
6. **Report.** Include the template permalink and the verification job
   permalink in the PIR or follow-up.

## Repo conventions for playbooks

Thin Ansible wrapper around stdlib-only Python (runs in the stock awx-ee
execution environment with zero extra dependencies):

```yaml
---
- name: my-diagnostic
  hosts: localhost
  connection: local
  gather_facts: false
  vars:
    service: gateway          # variables with defaults; exposed at launch
  tasks:
    - name: Run the check
      ansible.builtin.command:
        argv:
          - python3
          - "{{ playbook_dir }}/scripts/my_diagnostic.py"
          - "{{ service }}"
      register: check
      changed_when: false

    - name: Report
      ansible.builtin.debug:
        msg: "{{ check.stdout_lines }}"
```

- The Python script (in `scripts/`) uses **stdlib only** and must END with:
  `=== DIAGNOSTIC SUMMARY ===` / `result: healthy|unhealthy|error` /
  `detail: <one line>` — the block the investigation treats as authoritative.
- Templates are created with `ask_variables_on_launch` enabled so options can
  be passed as extra_vars.
- From AWX pods, the docker host is `host.k3d.internal` (not
  host.docker.internal) — parameterize target hosts.

## Hard rules

- **Propose before create.** Never call `create_job` (or imply a playbook is
  live) without a human's go-ahead, unless explicitly asked.
- **Diagnostics only.** Read-only checks; refuse remediation playbooks.
- New playbooks go through git review — never claim a playbook exists in AWX
  before its git change is merged and the project has synced.
- Every created template must be verified with a successful run before you
  cite it. Include permalinks.
