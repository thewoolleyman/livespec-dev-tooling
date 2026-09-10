"""Consumer-tier: the `SPECIFICATION/contracts.md` §"Reusable workflows wire contract".

The section states two things a consumer's `uses:` line depends on and nothing
else can supply: the FILE NAME is the semver-stable identifier, and the
workflow must declare the inputs the caller passes. It then names the minimum
shipped set — `reusable-check-matrix.yml`, whose `checks` input is a JSON-array
string the strategy matrixes over, each entry running the `run-check` composite
Action.

Asserted in three directions, each a distinct break:

- **The identifier is the path.** Every reusable workflow this repository ships
  sits at `.github/workflows/reusable-<name>.yml` and declares the
  `workflow_call` trigger. A file that lost the trigger still exists at its
  path, so a consumer's `uses:` reference resolves and then fails at run time
  with nothing in this repository having gone red — which is precisely why the
  trigger is asserted beside the name rather than assumed from it.
- **The `checks` input keeps its declared shape.** REQUIRED and typed `string`,
  because the caller passes a JSON-array STRING (`'["slug1", "slug2"]'`) and
  GitHub rejects a typed-`string` input passed an array — a type widened to
  `string` from something else, or an input quietly given a default, changes
  what every caller must send.
- **The wire actually reaches the check runner.** The strategy matrixes over
  `fromJSON(inputs.checks)` and each matrix entry runs this repository's own
  `run-check` composite Action. Without both, a workflow can declare the input
  correctly and run nothing per slug: the input would be accepted and silently
  ignored, and every consumer's check matrix would report green having executed
  no check.

The workflow file is read as TEXT rather than parsed: this library declares zero
runtime dependencies (`constraints.md` §"Dependencies") and ships no YAML
parser, and the assertions above are about line shapes GitHub itself fixes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"

# The path prefix the section makes the semver-stable identifier.
_REUSABLE_PREFIX = "reusable-"
_CALLABLE_TRIGGER = "workflow_call:"

# The named minimum-set member and the wire its callers depend on.
_CHECK_MATRIX = "reusable-check-matrix.yml"
_MATRIX_EXPANSION = "fromJSON(inputs.checks)"
_RUN_CHECK_ACTION = "/.github/actions/run-check"

# One `workflow_call` input entry: six-space name, eight-space fields.
_INPUT_ENTRY = "^      {name}:\n(?P<body>(?:        .*\n)+)"
_INPUT_FIELD = re.compile(r"^        (?P<field>[a-z-]+): ?(?P<value>.*)$", re.MULTILINE)

# What `checks` must declare, per the section's own description of it.
_CHECKS_INPUT_WIRE = {"required": "true", "type": "string"}


def _reusable_workflows() -> dict[str, str]:
    """Every shipped `reusable-*.yml`, keyed by the file name a `uses:` names."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(_WORKFLOWS_DIR.glob(f"{_REUSABLE_PREFIX}*.yml"))
    }


def _input_fields(*, source: str, name: str) -> dict[str, str]:
    """The declared fields of `source`'s `workflow_call` input `name`."""
    matched = re.search(_INPUT_ENTRY.format(name=re.escape(name)), source, re.MULTILINE)
    assert matched is not None, f"the workflow must declare a `{name}` `workflow_call` input"
    return {
        field.group("field"): field.group("value").strip().strip('"')
        for field in _INPUT_FIELD.finditer(matched.group("body"))
    }


def test_every_reusable_workflow_is_callable_at_the_path_that_identifies_it() -> None:
    """Each `reusable-*.yml` ships at its identifying path and declares `workflow_call`."""
    workflows = _reusable_workflows()
    assert workflows, (
        f"the library MUST ship at minimum one reusable workflow under "
        f"`.github/workflows/{_REUSABLE_PREFIX}<name>.yml`"
    )

    uncallable = sorted(
        name for name, source in workflows.items() if _CALLABLE_TRIGGER not in source
    )
    assert not uncallable, (
        f"a reusable workflow that lost its `{_CALLABLE_TRIGGER}` trigger still exists at "
        f"the path a consumer's `uses:` names, so the reference resolves and then fails at "
        f"run time with nothing here going red; uncallable={uncallable}"
    )
    assert _CHECK_MATRIX in workflows, (
        f"`{_CHECK_MATRIX}` is the named minimum shipped set, and its path IS the "
        f"semver-stable identifier consumers reference"
    )


def test_the_check_matrix_workflow_declares_its_input_and_runs_it_per_slug() -> None:
    """`checks` keeps its declared wire and the matrix reaches the `run-check` Action."""
    source = _reusable_workflows()[_CHECK_MATRIX]
    declared = _input_fields(source=source, name="checks")

    drifted = {
        field: (declared.get(field), expected)
        for field, expected in _CHECKS_INPUT_WIRE.items()
        if declared.get(field) != expected
    }
    assert not drifted, (
        f"the caller passes a JSON-array STRING, so `checks` must stay required and typed "
        f"`string`; drifted={drifted} declared={declared}"
    )

    assert _MATRIX_EXPANSION in source, (
        f"the strategy must matrix over the `checks` input (`{_MATRIX_EXPANSION}`), or the "
        f"input is accepted and silently ignored and the matrix runs nothing per slug"
    )
    assert _RUN_CHECK_ACTION in source, (
        f"each matrix entry must run this repository's own `run-check` composite Action — "
        f"the step that turns a slug into a `python -m` invocation; missing "
        f"`{_RUN_CHECK_ACTION}`"
    )
