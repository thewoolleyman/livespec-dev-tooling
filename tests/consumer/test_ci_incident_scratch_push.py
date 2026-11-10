"""Consumer-tier: a push to an incident-scratch/** branch runs ci.yml's master job graph.

Work item livespec-dev-tooling-7w757z. An incident drill's scratch observer binds
a scratch merge only to a real push run of `.github/workflows/ci.yml` on that
branch, so the push trigger admits `incident-scratch/**` beside `master`. Such a
push is meant to be indistinguishable from a master push in everything that
gates: the same jobs under the same job-level `if:`, the same `runs-on`
routing, and `incident-ci` selecting nothing so both incident flags stay
absent. That holds exactly when nothing that decides whether or where a job
runs reads the ref, so the tests below assert the trigger pair and the
ref-blindness of every job condition and every routing expression.

The one deliberate ref read is a STEP, not a job: export-telemetry's Honeycomb
export is master-only, so a drill run is never recorded as master CI. The job
itself still runs on every push and keeps master's job set. Any other ref read
in the workflow is a finding.

Each rule is a pure function of the parsed workflow, exercised against the real
ci.yml and against an in-memory negative control that must be caught.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"

# The push trigger's branch filter, in order: the default branch, then the drill branches.
_PUSH_BRANCHES = ["master", "incident-scratch/**"]

# A ref or branch read in an expression or in a shell line: the context refs,
# the push payload's own ref and base ref, and the repository's default branch.
_REF_READ = re.compile(
    "|".join(
        (
            r"github\.(?:ref|ref_name|head_ref|base_ref)\b",
            r"github\.event\.(?:ref|base_ref|repository\.default_branch)\b",
            r"\bGITHUB_(?:REF|REF_NAME|HEAD_REF|BASE_REF)\b",
        )
    )
)

# The single admitted ref read: export-telemetry's Honeycomb export step.
_EXPORT_JOB = "export-telemetry"
_EXPORT_STEP = "Export CI run telemetry to Honeycomb (closed-loop verified)"
_EXPORT_GUARD = "${{ github.ref == 'refs/heads/master' }}"
# The one admitted top-level ref read: the B' master-push concurrency block (constraints.md
# "CI matrix shape", v182; livespec-dev-tooling-qzw2gf), pinned whole. Its only ref read is the
# equality with refs/heads/master, so a master push joins the shared group while an
# incident-scratch/** push (like a pull request, a release commit, a principal revert and any
# Factory-Override push)
# resolves to its own run_id group: a scratch push is never grouped with, held by or dropped behind
# another run, and it runs master's complete job graph under master's job conditions and routing.
# Any other concurrency form, including cancel-in-progress true, is still a ref read and refused.
_BPRIME_CONCURRENCY = {
    "group": (
        "${{ github.workflow }}-${{ (github.event_name == 'push' && github.ref == 'refs/heads/master'"
        " && !startsWith(github.event.head_commit.message, 'chore(master): release')"
        " && !startsWith(github.event.head_commit.message, 'Revert complete incident PR #')"
        " && !contains(join(github.event.commits.*.message, ' '), 'Factory-Override:'))"
        " && 'master-push' || github.run_id }}"
    ),
    "cancel-in-progress": False,
}


def _load(*, text: str) -> dict[Any, Any]:
    return cast("dict[Any, Any]", yaml.safe_load(text))


def _triggers(*, workflow: dict[Any, Any]) -> dict[str, Any]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    raw = workflow.get("on", workflow.get(True))
    return cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}


def _jobs(*, workflow: dict[Any, Any]) -> dict[str, dict[str, Any]]:
    return cast("dict[str, dict[str, Any]]", workflow.get("jobs") or {})


def _steps(*, job: dict[str, Any]) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", job.get("steps") or [])


def _trigger_findings(*, workflow: dict[Any, Any]) -> list[str]:
    """What keeps the triggers from being exactly any-base PRs plus the two push patterns."""
    triggers = _triggers(workflow=workflow)
    findings: list[str] = []
    if sorted(str(name) for name in triggers) != ["pull_request", "push"]:
        findings.append(f"triggers are {sorted(str(name) for name in triggers)}")
    if triggers.get("pull_request") is not None:
        findings.append("pull_request carries a filter")
    push = cast("dict[str, Any]", triggers.get("push") or {})
    if push.get("branches") != _PUSH_BRANCHES:
        findings.append(f"push branches are {push.get('branches')}")
    extra = sorted(key for key in push if key != "branches")
    if extra:
        findings.append(f"push carries {extra}")
    return findings


def _ref_reads(*, workflow: dict[Any, Any]) -> list[str]:
    """Every place the workflow, a job or a step reads the ref, except the admitted export guard."""
    # Every top-level key but the triggers and `jobs` (env, concurrency,
    # defaults, permissions, run-name, ...) is scanned whole too: a workflow-
    # wide env value or concurrency group keyed on the ref splits scratch from
    # master as surely as a job condition does. `on` loads as True under YAML 1.1.
    reads: list[str] = [
        str(key)
        for key, value in workflow.items()
        if key not in ("on", True, "jobs")
        and _REF_READ.search(str(value))
        and not (key == "concurrency" and value == _BPRIME_CONCURRENCY)
    ]
    for name, job in _jobs(workflow=workflow).items():
        # Every job key but `steps` (if, runs-on, needs, strategy, outputs, env,
        # concurrency, continue-on-error, container, services, timeout-minutes,
        # with, ...) is scanned whole, so no key can be missed by an allowlist.
        for key, value in job.items():
            if key != "steps" and _REF_READ.search(str(value)):
                reads.append(f"{name}.{key}")
        for step in _steps(job=job):
            label = f"{name}/{step.get('name', step.get('id', '?'))}"
            admitted = (
                name == _EXPORT_JOB
                and step.get("name") == _EXPORT_STEP
                and step.get("if") == _EXPORT_GUARD
            )
            if not admitted and _REF_READ.search(str(step)):
                reads.append(label)
    return reads


def _export_findings(*, workflow: dict[Any, Any]) -> list[str]:
    """What keeps the Honeycomb export from being master-only inside a job every push runs."""
    job = _jobs(workflow=workflow).get(_EXPORT_JOB)
    if job is None:
        return [f"no {_EXPORT_JOB} job"]
    findings: list[str] = []
    if _REF_READ.search(str(job.get("if", ""))):
        findings.append("the job itself reads the ref, so a scratch push changes the job set")
    exports = [step for step in _steps(job=job) if step.get("name") == _EXPORT_STEP]
    if len(exports) != 1:
        findings.append(f"{len(exports)} export steps")
    elif exports[0].get("if") != _EXPORT_GUARD:
        findings.append(f"export step guard is {exports[0].get('if')!r}")
    return findings


def _real() -> dict[Any, Any]:
    return _load(text=_CI_WORKFLOW.read_text(encoding="utf-8"))


_CONTROL = """
on:
  pull_request:
  push:
    branches: [master, 'incident-scratch/**']
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: just check
  export-telemetry:
    if: ${{ !cancelled() && github.event_name == 'push' }}
    runs-on: ubuntu-latest
    steps:
      - name: Export CI run telemetry to Honeycomb (closed-loop verified)
        if: ${{ github.ref == 'refs/heads/master' }}
        run: bash export.sh
"""


def test_the_clean_control_passes_every_rule() -> None:
    """The control the negative cases mutate is itself clean, so each mutation alone is caught."""
    control = _load(text=_CONTROL)
    assert _trigger_findings(workflow=control) == []
    assert _ref_reads(workflow=control) == []
    assert _export_findings(workflow=control) == []


def test_ci_pushes_on_exactly_master_and_incident_scratch_and_prs_on_any_base() -> None:
    """The real trigger is the two push patterns plus the unfiltered pull_request."""
    assert _trigger_findings(workflow=_real()) == []


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("[master, 'incident-scratch/**']", "[master]"),
        ("[master, 'incident-scratch/**']", "[master, 'incident-scratch/**', 'feature/**']"),
        ("[master, 'incident-scratch/**']", "['**']"),
        ("  pull_request:\n", "  pull_request:\n    branches: [master]\n"),
        ("    branches: [master, 'incident-scratch/**']\n", "    branches-ignore: [wip]\n"),
        ("  pull_request:\n", "  pull_request:\n  workflow_dispatch:\n"),
    ],
)
def test_a_trigger_that_drops_widens_or_filters_is_caught(*, before: str, after: str) -> None:
    """Missing the scratch pattern, admitting any other branch, or filtering PRs is a finding."""
    mutated = _CONTROL.replace(before, after, 1)
    assert mutated != _CONTROL
    assert _trigger_findings(workflow=_load(text=mutated)) != []


def test_no_job_condition_routing_or_step_reads_the_ref_but_the_export_guard() -> None:
    """A scratch push gets master's job graph and runner routing: nothing gating reads the ref."""
    assert _ref_reads(workflow=_real()) == []


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            "  check:\n    if: ${{ github.ref == 'refs/heads/master' }}\n    runs-on: ubuntu-latest\n",
        ),
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            "  check:\n    runs-on: ${{ github.ref_name == 'master' && 'big' || 'small' }}\n",
        ),
        (
            "      - run: just check\n",
            "      - run: just check\n        if: ${{ github.ref == 'refs/heads/master' }}\n",
        ),
        (
            "      - run: just check\n",
            "      - run: '[ \"$GITHUB_REF\" = refs/heads/master ] && just check'\n",
        ),
        (
            "        run: bash export.sh\n",
            "        run: bash export.sh\n      - run: echo ${{ github.ref }}\n",
        ),
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            (
                "  check:\n    continue-on-error: ${{ github.ref != 'refs/heads/master' }}\n"
                "    runs-on: ubuntu-latest\n"
            ),
        ),
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            (
                "  check:\n    runs-on: ubuntu-latest\n"
                "    container:\n      image: ${{ github.ref_name == 'master' && 'a' || 'b' }}\n"
            ),
        ),
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            (
                "  check:\n    runs-on: ${{ github.event.repository.default_branch == 'master' "
                "&& 'big' || 'small' }}\n"
            ),
        ),
        (
            "      - run: just check\n",
            "      - run: echo ${{ github.event.ref }} && just check\n",
        ),
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            (
                "  check:\n    runs-on: ubuntu-latest\n"
                "    services:\n      cache:\n        image: ${{ github.ref_name }}\n"
            ),
        ),
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            (
                "  check:\n    runs-on: ubuntu-latest\n"
                "    timeout-minutes: ${{ github.ref == 'refs/heads/master' && 90 || 5 }}\n"
            ),
        ),
        (
            "  check:\n    runs-on: ubuntu-latest\n",
            "  check:\n    runs-on: ubuntu-latest\n    with:\n      branch: ${{ github.event.ref }}\n",
        ),
        ("jobs:\n", "env:\n  LANE: ${{ github.ref_name }}\njobs:\n"),
        (
            "jobs:\n",
            "concurrency:\n  group: ci-${{ github.ref }}\n  cancel-in-progress: true\njobs:\n",
        ),
    ],
)
def test_a_ref_read_outside_the_export_guard_is_caught(*, before: str, after: str) -> None:
    """A job condition, a routing expression or a step that reads the ref splits scratch from master."""
    mutated = _CONTROL.replace(before, after, 1)
    assert mutated != _CONTROL
    assert _ref_reads(workflow=_load(text=mutated)) != []


def _with_concurrency(*, group: str, cancel: str) -> dict[Any, Any]:
    block = f"concurrency:\n  group: >-\n    {group}\n  cancel-in-progress: {cancel}\njobs:\n"
    return _load(text=_CONTROL.replace("jobs:\n", block, 1))


def test_the_b_prime_master_push_concurrency_block_is_the_one_admitted_top_level_ref_read() -> None:
    """The pinned B' block keeps a scratch push in its own run_id group, so it splits nothing."""
    workflow = _with_concurrency(group=str(_BPRIME_CONCURRENCY["group"]), cancel="false")
    assert _ref_reads(workflow=workflow) == []


@pytest.mark.parametrize(
    ("group", "cancel"),
    [
        (str(_BPRIME_CONCURRENCY["group"]), "true"),
        (
            str(_BPRIME_CONCURRENCY["group"]).replace(
                "refs/heads/master", "refs/heads/incident-scratch"
            ),
            "false",
        ),
        ("${{ github.workflow }}-${{ github.ref }}", "false"),
    ],
)
def test_any_other_concurrency_form_that_reads_the_ref_is_still_caught(
    *, group: str, cancel: str
) -> None:
    """Only the exact pinned block is admitted: a cancelling, retargeted or ref-keyed group is refused."""
    assert _ref_reads(workflow=_with_concurrency(group=group, cancel=cancel)) == ["concurrency"]


def test_the_honeycomb_export_is_master_only_inside_a_job_every_push_runs() -> None:
    """export-telemetry keeps master's job set; only its export step is guarded on master."""
    assert _export_findings(workflow=_real()) == []


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("        if: ${{ github.ref == 'refs/heads/master' }}\n", ""),
        (
            "        if: ${{ github.ref == 'refs/heads/master' }}\n",
            "        if: ${{ github.event_name == 'push' }}\n",
        ),
        (
            "    if: ${{ !cancelled() && github.event_name == 'push' }}\n",
            "    if: ${{ !cancelled() && github.ref == 'refs/heads/master' }}\n",
        ),
        ("  export-telemetry:\n", "  telemetry:\n"),
        (
            "Export CI run telemetry to Honeycomb (closed-loop verified)",
            "Export CI run telemetry",
        ),
        (
            "        run: bash export.sh\n",
            (
                "        run: bash export.sh\n"
                "      - name: Export CI run telemetry to Honeycomb (closed-loop verified)\n"
                "        if: ${{ github.ref == 'refs/heads/master' }}\n"
                "        run: bash export.sh\n"
            ),
        ),
    ],
)
def test_an_unguarded_export_or_a_ref_gated_export_job_is_caught(
    *, before: str, after: str
) -> None:
    """A drill run reaching Honeycomb, or the job vanishing from a scratch run, is a finding."""
    mutated = _CONTROL.replace(before, after, 1)
    assert mutated != _CONTROL
    assert _export_findings(workflow=_load(text=mutated)) != []


def test_incident_ci_selects_incident_work_only_on_a_pull_request() -> None:
    """A push of any branch selects nothing, so `omitted` stays empty and both flags stay absent."""
    job = _jobs(workflow=_real())["incident-ci"]
    steps = {str(step.get("id")): step for step in _steps(job=job) if "id" in step}
    assert job["outputs"] == {"omitted": "${{ steps.entrance.outputs.omitted }}"}
    assert steps["entrance"]["if"] == "steps.select.outputs.block == 'present'"
    select = str(steps["select"]["run"])
    assert 'if [ "$GITHUB_EVENT_NAME" = "pull_request" ] && [ -n "$PR_NUMBER" ]; then' in select
    assert select.count("block=present") == 1
