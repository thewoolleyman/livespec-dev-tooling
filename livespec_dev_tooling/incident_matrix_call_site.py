"""The call-site rule: a caller wires reusable-check-matrix's incident inputs only from incident-ci.

`incident_matrix_omission` asks this module whether the workflow that CALLED
the matrix may omit anything. The workflow is parsed as YAML (`yaml.safe_load`),
never matched as text, so a quoted key, a space before the colon or a value on
the next line reads exactly as GitHub reads it.

Every job of a workflow whose `uses:` names `reusable-check-matrix.yml` is a
call site. A call site passes when ALL of these hold:

- `with.incident-omitted` is exactly `GUARDED_OMITTED` and
  `with.incident-ci-result` is exactly `GUARDED_RESULT`;
- no other `with:` key names an incident input (an `incident_omitted` or an
  `Incident-Omitted` is a finding, never silently ignored);
- the job `needs:` the `incident-ci` job, and the workflow has an
  `incident-ci` job.

At run time (`required=True`) the calling workflow must have at least one call
site and every call site must pass, because the matrix cannot tell which of a
workflow's jobs called it. `check_callers` applies the same per-job rule to
every workflow file, and there a call site that passes no incident input at all
has not adopted the inputs and is not a finding.

PyYAML is imported only when a workflow is parsed. Without it nothing parses,
so nothing passes: the reusable workflow's decision step installs it, pinned
by hash, into a throwaway virtual environment.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.budgeted_gh import GhRead

__all__: list[str] = [
    "GUARDED_OMITTED",
    "GUARDED_RESULT",
    "INCIDENT_JOB",
    "call_site_findings",
    "call_site_reason",
    "caller_path",
    "check_callers",
    "fetch_at",
    "load_workflow",
    "quoted",
]

INCIDENT_JOB = "incident-ci"
GUARDED_OMITTED = (
    "${{ needs.incident-ci.result == 'success' && needs.incident-ci.outputs.omitted || '[]' }}"
)
GUARDED_RESULT = "${{ needs.incident-ci.result }}"
_WIRED = {"incident-omitted": GUARDED_OMITTED, "incident-ci-result": GUARDED_RESULT}

_MATRIX_USES = re.compile(r"(?:^|/)\.github/workflows/reusable-check-matrix\.ya?ml(?:@|$)")
_WORKFLOW_PATH = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SHA = re.compile(r"[0-9a-f]{40}")
_MAX_CHARACTERS = 1048576


def quoted(*, value: str) -> str:
    """A caller value as one inert JSON string: no newline, no bare `%`."""
    return json.dumps(value).replace("%", "%25")


def load_workflow(*, text: str) -> dict[str, Any] | None:
    """The workflow as YAML reads it, or None when it is not a YAML mapping."""
    try:
        import yaml
    except ImportError:
        return None
    try:
        value: object = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError):
        return None
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _mapping(*, value: object) -> dict[Any, Any]:
    return cast("dict[Any, Any]", value) if isinstance(value, dict) else {}


def _job_findings(*, name: str, job: dict[Any, Any]) -> list[str]:
    inputs = _mapping(value=job.get("with"))
    findings = [
        f"job {quoted(value=name)}: {quoted(value=str(key))} is not an incident input of "
        "reusable-check-matrix.yml"
        for key in sorted(map(str, inputs))
        if "incident" in key.lower() and key not in _WIRED
    ]
    findings += [
        f"job {quoted(value=name)}: with.{key} is not exactly {expected}"
        for key, expected in _WIRED.items()
        if inputs.get(key) != expected
    ]
    needs = job.get("needs")
    names: object = [needs] if isinstance(needs, str) else needs
    if not isinstance(names, list) or INCIDENT_JOB not in cast("list[object]", names):
        findings.append(f"job {quoted(value=name)} does not need {INCIDENT_JOB}")
    return findings


def call_site_findings(*, workflow: dict[str, Any] | None, required: bool) -> list[str]:
    """Why the workflow's call sites may not omit; empty when every one passes."""
    jobs = _mapping(value=_mapping(value=workflow).get("jobs"))
    sites = {
        str(name): _mapping(value=job)
        for name, job in jobs.items()
        if _MATRIX_USES.search(str(_mapping(value=job).get("uses", "")))
    }
    adopted = {
        name: job
        for name, job in sites.items()
        if required
        or any("incident" in str(key).lower() for key in _mapping(value=job.get("with")))
    }
    findings = [
        f for name, job in sorted(adopted.items()) for f in _job_findings(name=name, job=job)
    ]
    if adopted and not isinstance(jobs.get(INCIDENT_JOB), dict):
        findings.append(f"the workflow has no {INCIDENT_JOB} job")
    if required and not sites:
        findings.append("no job of the workflow uses reusable-check-matrix.yml")
    return findings


def call_site_reason(
    *, caller: str | None, base_text: str | None, running_text: str | None
) -> str | None:
    """Why the calling workflow may not omit, or None when its trusted copy passes.

    `base_text` is the calling workflow at the pull request's base commit, the
    trusted revision; `running_text` is the copy GitHub ran, which must equal it.
    """
    name = quoted(value=caller or "")
    if caller is None or base_text is None:
        return f"the calling workflow {name} could not be read at the pull request's base"
    if running_text != base_text:
        return f"the pull request changes the calling workflow {name}"
    findings = call_site_findings(workflow=load_workflow(text=base_text), required=True)
    if findings:
        return f"the calling workflow {name} fails the call-site rule: {findings[0]}"
    return None


def caller_path(*, workflow_ref: str, repository: str) -> str | None:
    """The repository-relative path of the calling workflow, from `github.workflow_ref`."""
    rest = workflow_ref.removeprefix(f"{repository}/")
    path, at, _ref = rest.partition("@")
    if rest == workflow_ref or not at or _WORKFLOW_PATH.fullmatch(path) is None:
        return None
    return path


def fetch_at(*, repository: str, path: str, sha: str, read: Callable[..., GhRead]) -> str | None:
    """The file's text at one exact commit, read through the sanctioned `gh_read`, or None.

    `read` is `livespec_dev_tooling.budgeted_gh.gh_read` in production; `gh`
    authenticates with the caller's `GH_TOKEN`.
    """
    if not (
        _REPOSITORY.fullmatch(repository) and _WORKFLOW_PATH.fullmatch(path) and _SHA.fullmatch(sha)
    ):
        return None
    reply = read(
        args=[
            "api",
            "-H",
            "Accept: application/vnd.github.raw",
            f"repos/{repository}/contents/{path}?ref={sha}",
        ],
        timeout=30,
    )
    if reply.returncode != 0 or len(reply.stdout) > _MAX_CHARACTERS:
        return None
    return reply.stdout


def check_callers(*, paths: Sequence[Path]) -> list[str]:
    """The per-job call-site rule over workflow files; a call site with no incident input passes."""
    findings: list[str] = []
    for path in paths:
        workflow = load_workflow(text=path.read_text(encoding="utf-8"))
        if workflow is None:
            findings.append(f"{path}: not a YAML mapping (PyYAML is required to check it)")
            continue
        findings += [f"{path}: {f}" for f in call_site_findings(workflow=workflow, required=False)]
    return findings
