"""Rundeck Diagnostics Gateway.

A minimal MCP server (Streamable HTTP + static bearer token) that exposes
ONLY diagnostic-tagged Rundeck jobs to incident.io Investigations / Nexus.

Design notes live in docs/DESIGN.md. The short version: the general-purpose
Rundeck MCP server lets a caller run *any* job; an autonomous investigation
agent should only ever see read-only diagnostics, enforced server-side.

Environment:
    RUNDECK_URL             Rundeck base URL (default http://localhost:4440)
    RUNDECK_API_TOKEN       API token for a least-privilege gateway user (required)
    RUNDECK_PROJECT         Project to expose diagnostics from (required)
    RUNDECK_API_VERSION     API version (default 41)
    GATEWAY_BEARER_TOKEN    Token Nexus must present on every request (required)
    DIAGNOSTIC_TAG          Job tag that marks a job as a diagnostic (default "diagnostic")
    RUN_WAIT_SECONDS        Max seconds run_diagnostic waits for completion (default 120)
    LOG_TAIL_LINES          Max log lines returned to the agent (default 200)
    PORT                    Listen port (default 8710)
"""

from __future__ import annotations

import os
import sys
import time

import httpx
import uvicorn
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

RUNDECK_URL = os.environ.get("RUNDECK_URL", "http://localhost:4440").rstrip("/")
RUNDECK_API_TOKEN = os.environ.get("RUNDECK_API_TOKEN", "")
RUNDECK_PROJECT = os.environ.get("RUNDECK_PROJECT", "")
API_VERSION = os.environ.get("RUNDECK_API_VERSION", "41")
GATEWAY_BEARER_TOKEN = os.environ.get("GATEWAY_BEARER_TOKEN", "")
DIAGNOSTIC_TAG = os.environ.get("DIAGNOSTIC_TAG", "diagnostic")
RUN_WAIT_SECONDS = int(os.environ.get("RUN_WAIT_SECONDS", "120"))
LOG_TAIL_LINES = int(os.environ.get("LOG_TAIL_LINES", "200"))
PORT = int(os.environ.get("PORT", "8710"))

API = f"{RUNDECK_URL}/api/{API_VERSION}"

client = httpx.Client(
    headers={"X-Rundeck-Auth-Token": RUNDECK_API_TOKEN, "Accept": "application/json"},
    timeout=30.0,
)

mcp = FastMCP(
    "rundeck-diagnostics",
    instructions=(
        "Read-only diagnostic runbooks in Rundeck. Call list_diagnostics to see "
        "what is available, run_diagnostic to execute one, and "
        "get_diagnostic_result if a run is still in progress. These jobs only "
        "inspect system state — they never change it — so they are safe to run "
        "whenever their output would help an investigation."
    ),
)


def _diagnostic_jobs() -> list[dict]:
    resp = client.get(
        f"{API}/project/{RUNDECK_PROJECT}/jobs", params={"tags": DIAGNOSTIC_TAG}
    )
    resp.raise_for_status()
    return resp.json()


def _job_permalink(execution: dict) -> str:
    return execution.get("permalink") or f"{RUNDECK_URL}/execution/show/{execution['id']}"


def _log_tail(execution_id: int) -> str:
    resp = client.get(
        f"{API}/execution/{execution_id}/output",
        params={"lastlines": LOG_TAIL_LINES, "format": "json"},
    )
    resp.raise_for_status()
    entries = resp.json().get("entries", [])
    return "\n".join(e.get("log", "") for e in entries)


def _format_result(execution: dict, heading: str) -> str:
    execution_id = execution["id"]
    status = execution.get("status", "unknown")
    lines = [
        f"## {heading}",
        f"- Execution: #{execution_id} — **{status}**",
        f"- Job: {execution.get('job', {}).get('name', 'unknown')}",
        f"- Permalink (cite as evidence): {_job_permalink(execution)}",
    ]
    if status == "running":
        lines.append(
            f"\nStill running. Call get_diagnostic_result({execution_id}) before "
            "drawing conclusions — do not treat an in-flight diagnostic as evidence."
        )
    else:
        tail = _log_tail(execution_id)
        lines.append(f"\n### Output (last {LOG_TAIL_LINES} lines)\n```\n{tail}\n```")
    return "\n".join(lines)


@mcp.tool()
def list_diagnostics() -> str:
    """List the diagnostic runbooks available in Rundeck.

    Returns each job's id, name, and description. Descriptions explain when
    the diagnostic is useful and what output it produces. Use the id with
    run_diagnostic.
    """
    jobs = _diagnostic_jobs()
    if not jobs:
        return f"No jobs tagged '{DIAGNOSTIC_TAG}' found in project {RUNDECK_PROJECT}."
    lines = [f"# Diagnostic runbooks ({RUNDECK_PROJECT})", ""]
    for job in jobs:
        group = f"{job['group']}/" if job.get("group") else ""
        lines.append(f"- **{group}{job['name']}** (`{job['id']}`)")
        if job.get("description"):
            lines.append(f"  {job['description'].strip()}")
    return "\n".join(lines)


@mcp.tool()
def run_diagnostic(job_id: str, options: dict[str, str] | None = None) -> str:
    """Run a diagnostic runbook and return its output.

    Only jobs tagged as diagnostics can be run — these are read-only checks
    that inspect system state without changing it. Waits for completion (up
    to a bounded budget); if the job is still running when the budget is
    exhausted, returns the execution id to check with get_diagnostic_result.

    Args:
        job_id: Job UUID from list_diagnostics.
        options: Job option values, e.g. {"service": "payments-api"}.
    """
    allowed = {job["id"] for job in _diagnostic_jobs()}
    if job_id not in allowed:
        return (
            f"Refused: job {job_id} is not tagged '{DIAGNOSTIC_TAG}'. Only "
            "diagnostic runbooks can be run through this gateway. Call "
            "list_diagnostics to see what is available."
        )

    resp = client.post(f"{API}/job/{job_id}/run", json={"options": options or {}})
    if resp.status_code >= 400:
        return f"Rundeck rejected the run ({resp.status_code}): {resp.text[:500]}"
    execution = resp.json()
    execution_id = execution["id"]

    deadline = time.monotonic() + RUN_WAIT_SECONDS
    while time.monotonic() < deadline:
        state = client.get(f"{API}/execution/{execution_id}")
        state.raise_for_status()
        execution = state.json()
        if execution.get("status") != "running":
            break
        time.sleep(2)

    return _format_result(execution, "Diagnostic result")


@mcp.tool()
def get_diagnostic_result(execution_id: int) -> str:
    """Fetch the status and output of a previously started diagnostic run.

    Use when run_diagnostic reported the job was still running.
    """
    resp = client.get(f"{API}/execution/{execution_id}")
    resp.raise_for_status()
    return _format_result(resp.json(), "Diagnostic result (follow-up)")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {GATEWAY_BEARER_TOKEN}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def main() -> None:
    missing = [
        name
        for name, value in [
            ("RUNDECK_API_TOKEN", RUNDECK_API_TOKEN),
            ("RUNDECK_PROJECT", RUNDECK_PROJECT),
            ("GATEWAY_BEARER_TOKEN", GATEWAY_BEARER_TOKEN),
        ]
        if not value
    ]
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")

    app = mcp.http_app(middleware=[Middleware(BearerAuthMiddleware)])
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
