"""Consumer-tier: the `SPECIFICATION/constraints.md` §"CI matrix shape" contract.

The constraint calls itself consumer-observable and says why: a consumer's
branch-protection wiring names INDIVIDUAL MATRIX ENTRIES as required checks, so
deviating from the per-event matrix shape on a release breaks that wiring. Two
of its claims are decidable from the shipped CI surface, and each one breaks a
consumer in a different way:

- **The workflows this library SHIPS stay on GitHub-hosted capacity.** The
  constraint's words: the reusable check workflows "MUST NOT require the
  shared factory host's self-hosted labels". A consumer calling one of them
  has no such runner, and GitHub does not fall back when a self-hosted label
  set matches nothing — the job would sit unclaimed and the consumer's gate
  would wait forever on a check that never arrives. This is the half the
  shipped `self_hosted_routing` check does NOT cover: that check forbids a
  self-hosted FALLBACK behind a repo variable, which says nothing about a
  reusable workflow that names self-hosted capacity outright.
- **The matrix entry set does not vary by event.** Every gating matrix's
  `target:` list is a static literal, no gating job carries a job-level `if:`
  that could skip it on one event and not another, and the workflow triggers
  on `pull_request` and on `push` to `master` alike. Together those mean the
  same required-check names appear on a PR as on master. The mechanism that
  used to break this — a `detect-py-changes` job whose `py_changed` output
  gated the python jobs, letting a doc-only PR run FEWER checks than master —
  is asserted absent by name, along with the path filters that would subset
  the same way from the trigger instead.

Gating jobs are read as `ci-green`'s `needs:` list rather than guessed:
branch protection requires only that one context, so its dependencies ARE the
gate, and a job outside it (the telemetry export, which legitimately runs on
`push` alone) is correctly out of scope.

The constraint's remaining claim — that the inline `runs-on` fallback names
hosted capacity and never self-hosted — is the shipped `self_hosted_routing`
check's fail-closed-routing rule, armed against this repository's own
workflows, and is deliberately not restated here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_CI_WORKFLOW = _WORKFLOWS_DIR / "ci.yml"

# GitHub-hosted runner image families. A `runs-on` naming one of these is
# capacity every consumer has; anything else is a label set only some host
# carries.
_HOSTED_IMAGE_FAMILIES = ("ubuntu-", "windows-", "macos-")

# Markers that make a `runs-on` self-hosted — the literal group, this fleet's
# gating label, and the repo variable that resolves to a label set.
_SELF_HOSTED_MARKERS = ("self-hosted", "local-ci", "CI_RUNNER_LABELS")

_RUNS_ON = re.compile(r"^\s*runs-on:\s*(?P<value>.+?)\s*$", re.MULTILINE)

# Everything under the workflow's top-level `jobs:` key, so a 2-space key under
# `on:` (`pull_request:`) is never mistaken for a job name.
_JOBS_SECTION = re.compile(r"^jobs:\n(?P<body>.*)", re.MULTILINE | re.DOTALL)
_JOB_HEADER = re.compile(r"^  (?P<job>[a-z0-9-]+):$", re.MULTILINE)

# Job-level keys sit at four spaces; `needs:` is written as a flow sequence.
_NEEDS_LIST = re.compile(r"^    needs: \[(?P<members>[^\]]*)\]", re.MULTILINE)
_JOB_LEVEL_IF = re.compile(r"^    if:\s*(?P<expression>.+?)\s*$", re.MULTILINE)

# A matrix `target:` list and its entries, at their fixed indents.
_MATRIX_TARGETS = re.compile(r"^        target:\n(?P<body>(?:^          .*\n)*)", re.MULTILINE)
_TARGET_ENTRY = re.compile(r"^          - (?P<entry>.+?)\s*$", re.MULTILINE)

# The retired zero-`.py` subsetting mechanism, named so its return is caught,
# plus the trigger-level path filters that would subset the same way.
_SUBSETTING_MECHANISMS = ("py_changed", "detect-py-changes", "paths:", "paths-ignore:")

# The two events the gate must present the same matrix on.
_REQUIRED_TRIGGERS = ("  pull_request:\n", "  push:\n    branches: [master]\n")

# The gate job branch protection requires; its dependencies are the gating set.
_GATE_JOB = "  ci-green:\n"


def _without_comments(*, text: str) -> str:
    """`text` with every whole-line YAML comment removed.

    The shipped `self_hosted_routing` check learned this the same way: this
    workflow's own header explains, at length, the `detect-py-changes` /
    `py_changed` mechanism it RETIRED, so a raw substring scan convicts the
    file for documenting the thing it no longer does.
    """
    return "".join(f"{line}\n" for line in text.splitlines() if not line.lstrip().startswith("#"))


def _reusable_workflows() -> dict[str, str]:
    """Each shipped reusable workflow's filename mapped to its text."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_WORKFLOWS_DIR.glob("reusable-*.yml"))
    }


def _job_blocks(*, text: str) -> dict[str, str]:
    """Each job name in the workflow mapped to its block text."""
    section = _JOBS_SECTION.search(text)
    assert section is not None, "the workflow must declare a top-level `jobs:` key"
    body = section.group("body")
    headers = list(_JOB_HEADER.finditer(body))
    assert headers, "the workflow must declare at least one job"
    return {
        header.group("job"): body[
            header.end() : headers[index + 1].start() if index + 1 < len(headers) else len(body)
        ]
        for index, header in enumerate(headers)
    }


def _gating_job_names(*, text: str) -> list[str]:
    """The jobs `ci-green` depends on — the set branch protection gates on."""
    gate_index = text.find(_GATE_JOB)
    assert gate_index >= 0, "ci.yml must declare the `ci-green` gate job"
    needs = _NEEDS_LIST.search(text, gate_index)
    assert needs is not None, "the `ci-green` gate must declare its `needs:` list"
    return [member.strip() for member in needs.group("members").split(",")]


def test_the_shipped_reusable_workflows_stay_on_github_hosted_capacity() -> None:
    """No workflow this library ships requires a self-hosted label set."""
    workflows = _reusable_workflows()
    assert workflows, "the library must ship at least one reusable workflow"

    targeting = {
        name: sorted(
            value
            for value in _RUNS_ON.findall(text)
            if not value.startswith(_HOSTED_IMAGE_FAMILIES)
            or any(marker in value for marker in _SELF_HOSTED_MARKERS)
        )
        for name, text in workflows.items()
    }
    self_hosted = {name: values for name, values in targeting.items() if values}
    assert not self_hosted, (
        f"a reusable workflow this library ships to consumers must run on GitHub-hosted "
        f"capacity — a consumer has no self-hosted runner, and GitHub does not fall back "
        f"when a label set matches nothing, so its gate would wait on a check that never "
        f"arrives; self_hosted={self_hosted}"
    )


def test_the_gating_matrix_entry_set_is_identical_on_every_gated_event() -> None:
    """The required-check names a consumer wires appear the same on a PR as on master."""
    text = _without_comments(text=_CI_WORKFLOW.read_text(encoding="utf-8"))

    missing_triggers = sorted(trigger for trigger in _REQUIRED_TRIGGERS if trigger not in text)
    assert not missing_triggers, (
        f"the gating workflow must trigger on a pull_request exactly as on a push to "
        f"master, or the two gates cannot present the same matrix; "
        f"missing={missing_triggers}"
    )

    subsetting = sorted(name for name in _SUBSETTING_MECHANISMS if name in text)
    assert not subsetting, (
        f"zero-`.py` subsetting lets a doc-only pull request run FEWER checks than "
        f"master, so a required matrix entry a consumer names can go missing on one "
        f"event; found={subsetting}"
    )

    blocks = _job_blocks(text=text)
    gating = _gating_job_names(text=text)
    assert gating, "the `ci-green` gate must depend on at least one check-bearing job"
    unknown = sorted(name for name in gating if name not in blocks)
    assert not unknown, f"`ci-green` names a job the workflow does not declare; unknown={unknown}"

    conditioned = {
        name: sorted(_JOB_LEVEL_IF.findall(blocks[name]))
        for name in gating
        if _JOB_LEVEL_IF.search(blocks[name]) is not None
    }
    assert not conditioned, (
        f"a gating job carrying a job-level `if:` can be skipped on one event and run "
        f"on another, which drops its matrix entries from a consumer's required-check "
        f"set without failing anything; conditioned={conditioned}"
    )

    entries = [
        entry for block in _MATRIX_TARGETS.findall(text) for entry in _TARGET_ENTRY.findall(block)
    ]
    assert entries, "the gating CI must declare at least one per-target matrix entry"
    derived = sorted(entry for entry in entries if not entry.startswith("check-"))
    assert not derived, (
        f"every matrix target must be a literal `check-<slug>`; an expression-derived "
        f"entry could resolve differently per event and break the branch-protection "
        f"wiring that names it; derived={derived}"
    )
