"""The call-site rule: a caller wires reusable-check-matrix's incident inputs only from incident-ci.

`incident_matrix_omission` asks this module whether the workflow that CALLED
the matrix may omit anything. The workflow is parsed as YAML (`yaml.safe_load`),
never matched as text, so a quoted key, a space before the colon or a value on
the next line reads exactly as GitHub reads it.

At run time a call site is a job whose `uses:` is exactly the canonical
`thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@<ref>`
(owner and repo compared case-insensitively, as GitHub resolves them). A local
file merely NAMED `reusable-check-matrix.yml`, or that path under any other
owner, is not the matrix: it is a reusable workflow like any other, so the
nested walk below reads or refuses it (re-review of 2bfd031a, finding A).
`check_callers` lints the same call sites. A call site passes when ALL of
these hold:

- `with.incident-omitted` is exactly `GUARDED_OMITTED` and
  `with.incident-ci-result` is exactly `GUARDED_RESULT`;
- no other `with:` key names an incident input (an `incident_omitted` or an
  `Incident-Omitted` is a finding, never silently ignored);
- the job `needs:` the `incident-ci` job, and the workflow has an
  `incident-ci` job.

At run time (`required=True`) the calling workflow must have at least one call
site and every call site must pass, because the matrix cannot tell which of a
workflow's jobs called it.

`github.workflow_ref` names the TOP-LEVEL workflow, which may reach the matrix
through a reusable workflow of its own as well (re-review round 3). So at run
time `nested_reason` also walks every other job-level `uses:` of the top-level
workflow:

- a REMOTE reusable workflow (`owner/repo/...@ref`) refuses: it cannot be read
  to prove it never reaches the matrix;
- a LOCAL one (`./.github/workflows/<file>`) is read at the pull request's base
  commit, the copy that ran must equal it, and its own `uses:` are walked the
  same way, up to GitHub's four levels of workflows;
- the omission passes only if NO nested workflow calls the matrix, directly or
  transitively, because the leg cannot tell which call site it is.

Every unreadable, unparseable or unexpected shape refuses.

`check_callers` applies the same per-job rule to every workflow file, and there
a call site that passes no incident input at all has not adopted the inputs and
is not a finding.

A workflow with a duplicate mapping key or a `<<` merge key loads as None:
GitHub runs neither, so neither is read as anything at all. Keys are compared
twice: as raw scalars, case-insensitively (as GitHub compares `with:` keys),
and again as PyYAML resolves them. PyYAML reads keys by YAML 1.1, so `yes:` and
`on:` both load as True and the later silently replaces the earlier, while
GitHub reads both as string job ids (re-review of 2bfd031a, finding B). The
top-level `on:` alone resolves to True in every workflow and is no collision.

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
    "MAX_LEVELS",
    "call_site_findings",
    "call_site_reason",
    "caller_path",
    "check_callers",
    "fetch_at",
    "load_workflow",
    "nested_reason",
    "no_copies",
    "quoted",
    "workflow_copies",
]

INCIDENT_JOB = "incident-ci"
GUARDED_OMITTED = (
    "${{ needs.incident-ci.result == 'success' && needs.incident-ci.outputs.omitted || '[]' }}"
)
GUARDED_RESULT = "${{ needs.incident-ci.result }}"
_WIRED = {"incident-omitted": GUARDED_OMITTED, "incident-ci-result": GUARDED_RESULT}

_MATRIX_CALL = re.compile(
    r"(?i:thewoolleyman/livespec-dev-tooling)/\.github/workflows/reusable-check-matrix\.yml@[^\s@]+"
)
_WORKFLOW_PATH = re.compile(r"\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SHA = re.compile(r"[0-9a-f]{40}")
_MAX_CHARACTERS = 1048576
_LOCAL_USES = re.compile(r"\./(\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml)")
_MERGE_TAG = "tag:yaml.org,2002:merge"
# GitHub connects at most four levels of workflows: the caller and three nested.
MAX_LEVELS = 4


def quoted(*, value: str) -> str:
    """A caller value as one inert JSON string: no newline, no bare `%`."""
    return json.dumps(value).replace("%", "%25")


def _ambiguous(*, node: object, seen: set[int]) -> bool:
    """Whether a composed YAML node holds a merge key or a duplicate key, raw or resolved.

    A raw duplicate is compared case-folded. A resolved duplicate is two keys
    PyYAML constructs to one value, such as `yes` and `on` (both True); a
    non-scalar key never constructs to a hashable value, so it refuses too.
    """
    import yaml

    if id(node) in seen:
        return False
    seen.add(id(node))
    if isinstance(node, yaml.MappingNode):
        keys = [key for key, _value in node.value]
        names = {str(key.value).casefold() for key in keys}
        if any(key.tag == _MERGE_TAG for key in keys) or len(names) != len(keys):
            return True
        construct: Callable[[object], object] = cast("Any", yaml.SafeLoader("")).construct_object
        if len({construct(k) for k in keys if isinstance(k, yaml.ScalarNode)}) != len(keys):
            return True
        return any(_ambiguous(node=n, seen=seen) for pair in node.value for n in pair)
    if isinstance(node, yaml.SequenceNode):
        return any(_ambiguous(node=n, seen=seen) for n in node.value)
    return False


def load_workflow(*, text: str) -> dict[str, Any] | None:
    """The workflow as YAML reads it, or None when it is not an unambiguous YAML mapping."""
    try:
        import yaml
    except ImportError:
        return None
    try:
        if _ambiguous(node=yaml.SafeLoader(text).get_single_node(), seen=set()):
            return None
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
        if _MATRIX_CALL.fullmatch(str(_mapping(value=job).get("uses", "")))
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


def no_copies(*, path: str) -> tuple[str | None, str | None]:
    """A reader that can read no nested workflow, so any nested workflow refuses."""
    _ = path
    return None, None


def workflow_copies(
    *, path: str, repository: str, sha: str, workspace: str, read: Callable[..., GhRead]
) -> tuple[str | None, str | None]:
    """A workflow's copy at the base commit (from the forge) and the copy that ran (on disk)."""
    running = None
    if workspace and _WORKFLOW_PATH.fullmatch(path):
        try:
            running = (Path(workspace) / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            running = None
    return fetch_at(repository=repository, path=path, sha=sha, read=read), running


def _jobs_uses(*, workflow: dict[str, Any]) -> list[object]:
    jobs = _mapping(value=workflow.get("jobs"))
    return [_mapping(value=job)["uses"] for job in jobs.values() if "uses" in _mapping(value=job)]


def nested_reason(
    *,
    workflow: dict[str, Any],
    copies: Callable[..., tuple[str | None, str | None]],
    level: int = 1,
) -> str | None:
    """Why a reusable workflow below `workflow` may reach the matrix; None when none can."""
    for uses in _jobs_uses(workflow=workflow):
        text = quoted(value=str(uses))
        if level == 1 and _MATRIX_CALL.fullmatch(str(uses)):
            continue
        local = _LOCAL_USES.fullmatch(uses) if isinstance(uses, str) else None
        if local is None:
            return f"calls a reusable workflow that may reach the matrix unchecked: {text}"
        if level >= MAX_LEVELS:
            return f"nests reusable workflows beyond GitHub's {MAX_LEVELS} levels: {text}"
        base, running = copies(path=local.group(1))
        nested = load_workflow(text=base) if base is not None and running == base else None
        if nested is None:
            return f"calls {text}, which is unreadable at the base or changed by the PR"
        reason = nested_reason(workflow=nested, copies=copies, level=level + 1)
        if reason is not None:
            return reason
    return None


def call_site_reason(
    *,
    caller: str | None,
    base_text: str | None,
    running_text: str | None,
    copies: Callable[..., tuple[str | None, str | None]] = no_copies,
) -> str | None:
    """Why the calling workflow may not omit, or None when its trusted copy passes.

    `base_text` is the calling workflow at the pull request's base commit, the
    trusted revision; `running_text` is the copy GitHub ran, which must equal it.
    `copies` reads a nested workflow's two copies for `nested_reason`.
    """
    name = quoted(value=caller or "")
    if caller is None or base_text is None:
        return f"the calling workflow {name} could not be read at the pull request's base"
    if running_text != base_text:
        return f"the pull request changes the calling workflow {name}"
    workflow = load_workflow(text=base_text)
    findings = call_site_findings(workflow=workflow, required=True)
    if findings:
        return f"the calling workflow {name} fails the call-site rule: {findings[0]}"
    reason = nested_reason(workflow=workflow or {}, copies=copies)
    return None if reason is None else f"the calling workflow {name} {reason}"


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
