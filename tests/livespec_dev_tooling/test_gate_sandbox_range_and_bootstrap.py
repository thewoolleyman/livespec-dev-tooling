"""The delegated-gate sandbox provisions a RANGE, a diff base, and a bootstrap.

`ci-runner/k3s/phase2/gates/gate-job-template.yaml` used to `git init` an empty
workspace and fetch ONE ref at `--depth 1`. That produces a checkout with the
right tree and nothing else: no ancestry, no `origin/master`, and none of the
files `just bootstrap` materialises. Eight members of the aggregate then failed
STRUCTURALLY rather than judging the tree — the shipped-path release guard on
`range_base_unresolvable`, both coverage-diff members and the live-handoff-file
member on an absent `origin/master`, red-green-replay's range arm on an absent
commit range, and the commit-refuse-hook, worktree-pack and workflow-edit
members on files that were never installed.

WHY THIS IS A TEST AND NOT A COMMENT. Every one of those failures reads as a RED
GATE. The Job runs, the aggregate runs, members fail, the client reports
`Failed` — the exact shape a genuinely broken tree produces. Nothing in the
delegated path can tell an operator that the gate judged the sandbox instead of
the code, so the property has to be pinned where it can fail loudly: here.

These tests read the REAL template and RUN the real renderer's exit-test suite;
they contact no cluster, push to no mirror, and apply nothing.

Work-item livespec-dev-tooling-rwmo.1 (plan livespec
`k3s-on-gmktec-for-vps-usage`, epic `livespec-sab5gn`; design in that plan's
research/003 sections D and E).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_dev_tooling import gate_remote_client

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATES = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates"
_TEMPLATE = _GATES / "gate-job-template.yaml"
_EXIT_TESTS = _GATES / "render-gate-job-exit-tests.sh"

# The renderer substitutes this marker everywhere it appears, so the refspecs
# below are asserted in their UNRENDERED form — which is the form a reader of
# the template edits, and the only form that is wrong in exactly one place.
_TREE_TOKEN = "@@TREE_HASH@@"


def _template_lines() -> list[str]:
    return _TEMPLATE.read_text(encoding="utf-8").splitlines()


def _executable_lines() -> list[str]:
    """Template lines with every comment dropped.

    The template explains at length WHY it no longer takes a `--depth 1` fetch,
    and prose about a flag must never read as the flag: a comment-blind
    assertion would pass on a template that had been reverted and still carried
    its own explanation.
    """
    return [line for line in _template_lines() if not line.lstrip().startswith("#")]


def _gate_container_script() -> list[str]:
    """The gate container's own lines, comments dropped.

    Sliced from `- name: gate` to the end of the file so the initContainer
    above cannot contribute to an assertion about what the AGGREGATE container
    runs. `next` raises when the container is gone, which is a bug in the
    template rather than a state to report.
    """
    lines = _template_lines()
    start = next(index for index, line in enumerate(lines) if line.strip() == "- name: gate")
    return [line for line in lines[start:] if not line.lstrip().startswith("#")]


def test_the_gate_job_fetches_ancestry_rather_than_a_single_shallow_commit() -> None:
    """`--depth` anywhere in the fetch is the defect this slice removed.

    A shallow tip has no parents, so `origin/master..HEAD` is not a range that
    can be walked and `git merge-base` has nothing to walk to — which is why the
    flag's absence is asserted rather than merely the refspecs' presence.
    """
    shallow = [line for line in _executable_lines() if "--depth" in line]
    assert shallow == [], f"the gate fetch is still shallow: {shallow}"
    joined = "\n".join(_executable_lines())
    assert f'"+refs/gates/{_TREE_TOKEN}:refs/gates/{_TREE_TOKEN}"' in joined


def test_the_base_companion_ref_lands_where_every_range_member_looks_for_it() -> None:
    """`origin/master` is the literal name eight members resolve, so it is the
    name the fetch has to write — and the merge-base is asserted in the pod.

    Present is not the same as USABLE: two refs with no common ancestor satisfy
    every other check the initContainer makes and still leave the aggregate
    without a diff base, so the initContainer takes the merge-base itself and
    fails there, where the message names the cause.
    """
    joined = "\n".join(_executable_lines())
    assert f'"+refs/gates/{_TREE_TOKEN}.base:refs/remotes/origin/master"' in joined
    assert "git merge-base HEAD origin/master" in joined


def test_the_template_and_the_client_spell_the_base_ref_suffix_identically() -> None:
    """The one seam this design has: two files, two languages, one ref name.

    The client names the companion ref and the pod fetches it, and neither can
    see the other. A drifted suffix is not a syntax error anywhere — it is a
    fetch that finds nothing, at gate time, on the cluster.
    """
    assert hasattr(
        gate_remote_client, "GATE_BASE_REF_SUFFIX"
    ), "the client does not name a base-ref suffix for the template to agree with"
    suffix = gate_remote_client.GATE_BASE_REF_SUFFIX
    joined = "\n".join(_executable_lines())
    assert f'"+refs/gates/{_TREE_TOKEN}{suffix}:refs/remotes/origin/master"' in joined


def test_the_repository_bootstrap_precedes_the_aggregate_in_the_gate_container() -> None:
    """Both installs, then `just hook_gate=1 check` — in that order and nothing else.

    Asserted as the WHOLE list rather than as three memberships, so it also
    pins that the aggregate is the last thing the container runs and that it is
    the PRE-PUSH aggregate the gate stands in for: `just hook_gate=1 check`, the
    command `check-pre-push.sh` runs. `hook_gate` adds `hook_gate_skips` (today
    just `check-fleet-conformance-admin`, which needs a user-class admin
    credential no pre-push host or gate pod holds) to the skip set; bare
    `just check` ran it and failed the gate on a target the local pre-push never
    runs.
    """
    steps = [line.strip() for line in _gate_container_script() if line.strip().startswith("just ")]
    assert steps == [
        "just install-worktree-pack",
        "just install-commit-refuse-hooks",
        "just hook_gate=1 check",
    ]


def test_the_renderers_own_exit_test_suite_passes() -> None:
    """Run the shell suite that proves the RENDERED manifest carries all of it.

    The template is a template: everything above reads its unrendered source,
    and a substitution bug would leave every assertion here true and the
    manifest wrong. The suite renders against its own fixture repositories and
    mutates the template to prove each of its cases can fail, so running it from
    pytest is what puts that evidence under `just check` rather than under an
    operator who remembers to invoke it.
    """
    completed = subprocess.run(
        [str(_EXIT_TESTS)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
