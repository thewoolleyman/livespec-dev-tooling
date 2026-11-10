"""A reusable workflow nested under the caller can never carry an omission past the call-site rule.

Work-item livespec-dev-tooling-hlxbsv, round 3 of the review of
livespec-dev-tooling#3966 (issuecomment-6764386001). `github.workflow_ref` names
the TOP-LEVEL workflow. A `ci.yml` with one guarded direct call could also reach
the matrix through `uses: ./.github/workflows/wrapper.yml`, and a PR could edit
that wrapper while `ci.yml` stayed identical to the base. The decision now walks
every other job-level `uses:` of the top-level workflow: a remote reusable
workflow refuses; a local one is read at the base, must equal the copy that ran,
and is walked in turn up to GitHub's four levels; and any nested workflow that
reaches the matrix refuses. A harmless local reusable workflow still omits.
Every case runs through `main()` with the runner's environment, real workspace
copies and a forge read per path, beside the authorized negative control.

Re-review of 2bfd031a, finding A: ONLY the canonical
`thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@<ref>`
(owner and repo case-insensitive) is the matrix call site. A local file merely
named `reusable-check-matrix.yml`, or the same path under another owner, is a
reusable workflow like any other: walked when local, refused when remote.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_matrix_omission
from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.incident_matrix_call_site import GUARDED_OMITTED, GUARDED_RESULT

__all__: list[str] = []

_REPOSITORY = "owner/repo"
_BASE = "b" * 40
_MATRIX = "thewoolleyman/livespec-dev-tooling/.github/workflows/reusable-check-matrix.yml@v1"
_LOCAL_MATRIX = "./.github/workflows/reusable-check-matrix.yml"
_OTHER_OWNER = "evil/x/.github/workflows/reusable-check-matrix.yml@main"
_MATRIX_CASED = "TheWoolleyman/LiveSpec-Dev-Tooling/.github/workflows/reusable-check-matrix.yml@v1"


def _guarded(*, uses: str, name: str = "shared") -> str:
    """One job that passes incident-ci's guarded pair to `uses`."""
    return (
        f"  {name}:\n    needs: [incident-ci]\n    uses: {uses}\n    with:\n"
        f"      incident-omitted: {GUARDED_OMITTED}\n      incident-ci-result: {GUARDED_RESULT}\n"
    )


_INCIDENT_CI = "jobs:\n  incident-ci:\n    runs-on: ubuntu-latest\n"
_DIRECT = _INCIDENT_CI + _guarded(uses=_MATRIX)
_LITERAL_CALL = (
    f"on: workflow_call\njobs:\n  sneaky:\n    uses: {_MATRIX}\n    with:\n"
    "      incident-omitted: '[\"check-per-file-coverage\"]'\n      incident-ci-result: success\n"
)
_HARMLESS = (
    "on: workflow_call\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: [{run: make}]\n"
)


def _calls(*names: str) -> str:
    """A reusable workflow whose jobs call these local workflows."""
    jobs = "".join(f"  to-{n}:\n    uses: ./.github/workflows/{n}.yml\n" for n in names)
    return "on: workflow_call\njobs:\n" + jobs


def _with_job(*, uses: str) -> str:
    return _DIRECT + f"  wrapped:\n    uses: {uses}\n"


def _run(tmp_path: Path, *, base: dict[str, str], running: dict[str, str] | None = None):
    """One decision run: `base` maps workflow file names to their base copies."""
    workflows = tmp_path / "workspace" / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    for name, text in (running or base).items():
        (workflows / name).write_text(text, encoding="utf-8")
    event = tmp_path / "event.json"
    pull_request = {
        "labels": [{"name": "expedited-incident-response"}],
        "head": {"repo": {"full_name": _REPOSITORY}},
        "base": {"repo": {"full_name": _REPOSITORY}, "sha": _BASE},
    }
    event.write_text(json.dumps({"pull_request": pull_request}), encoding="utf-8")
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")

    def forge(**kwargs: object) -> GhRead:
        name = str(kwargs["args"]).split("/.github/workflows/")[1].split("?ref=")[0]
        found = base.get(name)
        return GhRead(returncode=0 if found is not None else 1, stdout=found or "", stderr="")

    code = incident_matrix_omission.main(
        argv=[],
        environ={
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_EVENT_PATH": str(event),
            "GITHUB_REPOSITORY": _REPOSITORY,
            "GITHUB_WORKSPACE": str(workflows.parents[1]),
            "GITHUB_OUTPUT": str(output),
            "CALLER_WORKFLOW_REF": f"{_REPOSITORY}/.github/workflows/ci.yml@refs/pull/7/merge",
            "INCIDENT_CI_RESULT": "success",
            "INCIDENT_OMITTED": '["check-per-file-coverage"]',
            "MATRIX_CHECK": "per_file_coverage",
        },
        read=Mock(side_effect=forge),
    )
    return code, output.read_text(encoding="utf-8")


_OMITS = (0, "omit=true\n")
_RUNS = (0, "omit=false\n")


@pytest.mark.parametrize(
    ("base", "running", "expected"),
    [
        ({"ci.yml": _DIRECT}, None, _OMITS),
        (
            {"ci.yml": _with_job(uses="./.github/workflows/wrapper.yml"), "wrapper.yml": _HARMLESS},
            None,
            _OMITS,
        ),
        (
            {
                "ci.yml": _with_job(uses="./.github/workflows/wrapper.yml"),
                "wrapper.yml": _LITERAL_CALL,
            },
            None,
            _RUNS,
        ),
        (
            {"ci.yml": _with_job(uses="./.github/workflows/wrapper.yml"), "wrapper.yml": _HARMLESS},
            {
                "ci.yml": _with_job(uses="./.github/workflows/wrapper.yml"),
                "wrapper.yml": _LITERAL_CALL,
            },
            _RUNS,
        ),
        ({"ci.yml": _with_job(uses="other/repo/.github/workflows/x.yml@v1")}, None, _RUNS),
        ({"ci.yml": _with_job(uses="./.github/workflows/missing.yml")}, None, _RUNS),
        (
            {
                "ci.yml": _with_job(uses="./.github/workflows/a.yml"),
                "a.yml": _calls("b"),
                "b.yml": _LITERAL_CALL,
            },
            None,
            _RUNS,
        ),
        (
            {
                "ci.yml": _with_job(uses="./.github/workflows/a.yml"),
                "a.yml": _calls("b"),
                "b.yml": _calls("c"),
                "c.yml": _HARMLESS,
            },
            None,
            _OMITS,
        ),
        (
            {
                "ci.yml": _with_job(uses="./.github/workflows/a.yml"),
                "a.yml": _calls("b"),
                "b.yml": _calls("c"),
                "c.yml": _calls("d"),
                "d.yml": _HARMLESS,
            },
            None,
            _RUNS,
        ),
        ({"ci.yml": _DIRECT + "  shared:\n    runs-on: ubuntu-latest\n"}, None, _RUNS),
        ({"ci.yml": "x: &m {a: 1}\n" + _DIRECT + "  merged:\n    <<: *m\n"}, None, _RUNS),
        (
            {
                "ci.yml": _INCIDENT_CI + _guarded(uses=_LOCAL_MATRIX),
                "reusable-check-matrix.yml": _HARMLESS,
            },
            {
                "ci.yml": _INCIDENT_CI + _guarded(uses=_LOCAL_MATRIX),
                "reusable-check-matrix.yml": _LITERAL_CALL,
            },
            _RUNS,
        ),
        (
            {
                "ci.yml": _DIRECT + _guarded(uses=_LOCAL_MATRIX, name="local"),
                "reusable-check-matrix.yml": _HARMLESS,
            },
            {
                "ci.yml": _DIRECT + _guarded(uses=_LOCAL_MATRIX, name="local"),
                "reusable-check-matrix.yml": _LITERAL_CALL,
            },
            _RUNS,
        ),
        (
            {
                "ci.yml": _DIRECT + _guarded(uses=_LOCAL_MATRIX, name="local"),
                "reusable-check-matrix.yml": _HARMLESS,
            },
            None,
            _OMITS,
        ),
        ({"ci.yml": _INCIDENT_CI + _guarded(uses=_OTHER_OWNER)}, None, _RUNS),
        ({"ci.yml": _DIRECT + _guarded(uses=_OTHER_OWNER, name="other")}, None, _RUNS),
        ({"ci.yml": _INCIDENT_CI + _guarded(uses="evil/" + _MATRIX)}, None, _RUNS),
        ({"ci.yml": _INCIDENT_CI + _guarded(uses=_MATRIX_CASED)}, None, _OMITS),
    ],
    ids=[
        "direct-only",
        "harmless-local-reusable-still-omits",
        "wrapper-passes-literals",
        "pr-edits-wrapper-with-ci-unchanged",
        "remote-reusable",
        "unreadable-local-reusable",
        "chain-reaching-matrix-two-levels-down",
        "harmless-chain-at-the-four-level-limit",
        "chain-beyond-four-levels",
        "duplicate-job-key",
        "merge-key",
        "p1-local-file-named-matrix-is-the-only-call",
        "p1-pr-edits-a-local-file-named-matrix-beside-the-direct-call",
        "unchanged-harmless-local-file-named-matrix-still-omits",
        "p2-other-owner-matrix-is-the-only-call",
        "p2-other-owner-matrix-beside-the-direct-call",
        "canonical-path-under-another-owner",
        "canonical-owner-and-repo-case-insensitive",
    ],
)
def test_only_a_caller_with_no_unchecked_route_to_the_matrix_omits(
    tmp_path, base, running, expected
):
    assert _run(tmp_path, base=base, running=running) == expected
