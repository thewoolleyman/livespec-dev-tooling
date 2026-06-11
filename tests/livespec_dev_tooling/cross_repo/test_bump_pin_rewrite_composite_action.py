"""Fixture test for the `bump-pin-rewrite` composite Action invocation surface.

Per `SPECIFICATION/contracts.md` §"Composite Actions wire contract"
and §"Cross-repo coordination automation surface", the
`.github/actions/bump-pin-rewrite/action.yml` composite Action is the
shared pin-rewrite + commit + auto-merge-PR-open body for both
`reusable-bump-pin-from-dispatch.yml` and `reusable-pin-freshness.yml`.

The extraction (per li-b4yiuv) collapses the previously-duplicated
rewrite step block — case-block over the four `pin_format` values plus
the surrounding vendor-update / just-check / commit-push / open-PR
tail — into one composite Action whose `inputs:` schema is a strict
superset of both callers' needs.

This test asserts the shape statically without pulling in PyYAML
(intentionally absent from the project's deps per
SPECIFICATION/non-functional-requirements.md): the assertions are
text-based pattern-matches against the YAML source files. The
composite Action's input schema, both reusable workflows' invocation
of the Action with every required input wired, and that the
case-block over the four pin formats is no longer inlined into either
workflow are all verified by literal-string presence/absence checks.

Coverage target: the composite Action's invocation surface in YAML.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_ACTION_PATH = _REPO_ROOT / ".github" / "actions" / "bump-pin-rewrite" / "action.yml"
_BUMP_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "reusable-bump-pin-from-dispatch.yml"
_FRESHNESS_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "reusable-pin-freshness.yml"

# Inputs the composite Action MUST declare. Strict superset of the
# union of both callers' needs per the work-item's instruction.
_REQUIRED_ACTION_INPUTS = (
    "source_repo",
    "tag",
    "records",
    "branch_prefix",
    "pr_body",
    "app_token",
    "app_slug",
)

# The composite Action MUST be invoked via this relative path from a
# reusable workflow per the GitHub-Actions semantics for `./`-paths in
# reusable workflows (resolved against the caller's GITHUB_WORKSPACE,
# NOT the reusable workflow's own repo). The `.livespec-dev-tooling/`
# subdir is where the `Checkout livespec-dev-tooling support modules`
# step clones this repo on the caller side.
_COMPOSITE_USES_PATH = "./.livespec-dev-tooling/.github/actions/bump-pin-rewrite"

# The four pin formats from SPECIFICATION/contracts.md §"Pin
# autodiscovery rules" — every case-arm value the rewrite step
# dispatches on.
_PIN_FORMAT_CASE_ARMS = (
    "livespec_jsonc_compat_pinned)",
    "pyproject_toml_uv_sources)",
    "vendor_jsonc)",
    "copier_answers_commit)",
)

# Per livespec-dev-tooling-8ml: the calling reusable workflows check out
# this repo's support modules to `./.livespec-dev-tooling` — a nested git
# repo inside the consumer work tree. The "Commit + push bump branch" step
# runs `git add -A`, which would stage that nested checkout as a stray
# gitlink (mode 160000) with no `.gitmodules` entry and commit it onto the
# consumer's master (observed on the v0.12.0 fan-out). The fix adds (1) a
# local `info/exclude` entry for the checkout BEFORE `git add -A` and (2) a
# defense-in-depth guard AFTER `git add -A` that refuses to commit any
# staged gitlink. Both live in the composite Action's commit step.
_GITLINK_EXCLUDE_ENTRY = "/.livespec-dev-tooling/"
_GITLINK_EXCLUDE_TARGET = "info/exclude"
# The guard keys on the gitlink mode 160000 anchored as a grep pattern;
# matching the anchored form (not the bare digits) avoids a false match
# against the "(mode 160000)" prose in the surrounding `#` comments.
_GITLINK_GUARD_MODE = "160000"
_GITLINK_GUARD_GREP = "^160000$"


def _read(*, path: Path) -> str:
    """Read a UTF-8 text file."""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Composite Action surface
# ---------------------------------------------------------------------------


def test_composite_action_file_exists() -> None:
    """The composite Action source file exists at the spec-pinned path."""
    assert _ACTION_PATH.is_file(), f"missing composite Action: {_ACTION_PATH}"


def test_composite_action_declares_required_inputs() -> None:
    """The composite Action declares every required input as a strict superset of caller needs."""
    text = _read(path=_ACTION_PATH)
    # The `inputs:` block is a top-level mapping; each input's name
    # appears as a 2-space-indented key under it.
    inputs_block_match = re.search(r"^inputs:\s*\n((?:[ \t]+[^\n]*\n)+)", text, re.MULTILINE)
    assert inputs_block_match, "composite Action has no top-level `inputs:` block"
    inputs_block = inputs_block_match.group(1)
    for name in _REQUIRED_ACTION_INPUTS:
        # 2-space-indented `<name>:` key inside the inputs block.
        assert re.search(
            rf"^  {re.escape(name)}:\s*$", inputs_block, re.MULTILINE
        ), f"composite Action missing required input: {name!r}"


def test_composite_action_inputs_all_required_true() -> None:
    """Every declared input MUST be `required: true` per the strict-superset contract."""
    text = _read(path=_ACTION_PATH)
    for name in _REQUIRED_ACTION_INPUTS:
        # The input's nested fields are 4-space-indented; require the
        # `required: true` field within the same input block.
        # Use a non-greedy lookahead until the next 2-space-indented
        # key or EOF.
        block_match = re.search(
            rf"^  {re.escape(name)}:\s*\n((?:    [^\n]*\n)+)",
            text,
            re.MULTILINE,
        )
        assert block_match, f"could not parse input block for {name!r}"
        input_body = block_match.group(1)
        assert re.search(r"^    required:\s*true\s*$", input_body, re.MULTILINE), (
            f"composite Action input {name!r} MUST be required: true "
            f"(both callers wire every input on every invocation)"
        )


def test_composite_action_is_composite_using_runs() -> None:
    """The composite Action declares `runs: { using: composite, ... }`."""
    text = _read(path=_ACTION_PATH)
    assert re.search(r"^runs:\s*$", text, re.MULTILINE), "missing top-level `runs:` block"
    assert re.search(
        r"^\s+using:\s+composite\s*$", text, re.MULTILINE
    ), "composite Action `runs.using` MUST be `composite`"
    assert re.search(
        r"^\s+steps:\s*$", text, re.MULTILINE
    ), "composite Action MUST declare `runs.steps`"


# ---------------------------------------------------------------------------
# Caller invocation surface
# ---------------------------------------------------------------------------


def _assert_workflow_invokes_composite(*, workflow_path: Path, expected_branch_prefix: str) -> None:
    """Assert a reusable workflow invokes the composite Action with every required input."""
    text = _read(path=workflow_path)
    # The composite Action is invoked via `uses: <path>`.
    uses_count = text.count(f"uses: {_COMPOSITE_USES_PATH}")
    assert uses_count == 1, (
        f"{workflow_path.name}: expected exactly 1 invocation of "
        f"{_COMPOSITE_USES_PATH!r}, found {uses_count}"
    )
    # Capture the `with:` block following the `uses:` line. The block
    # ends at the next top-level step (` - name:` or end-of-file).
    invocation_match = re.search(
        re.escape(f"uses: {_COMPOSITE_USES_PATH}") + r"\s*\n\s*with:\s*\n((?:[ \t]+[^\n]*\n)+)",
        text,
    )
    assert invocation_match, f"{workflow_path.name}: composite invocation missing `with:` block"
    with_block = invocation_match.group(1)
    for name in _REQUIRED_ACTION_INPUTS:
        # Each input is provided as `<name>: <value>` at the
        # workflow's `with:` indentation.
        assert re.search(
            rf"\b{re.escape(name)}:\s*", with_block
        ), f"{workflow_path.name}: composite invocation missing input {name!r}"
    # Branch-prefix value pins this workflow's naming convention.
    assert re.search(
        rf"\bbranch_prefix:\s*{re.escape(expected_branch_prefix)}\s*$",
        with_block,
        re.MULTILINE,
    ), (
        f"{workflow_path.name}: composite invocation `branch_prefix:` MUST be "
        f"{expected_branch_prefix!r}"
    )


def test_bump_from_dispatch_workflow_invokes_composite_action() -> None:
    """`reusable-bump-pin-from-dispatch.yml` invokes the composite Action exactly once."""
    _assert_workflow_invokes_composite(
        workflow_path=_BUMP_WORKFLOW_PATH,
        expected_branch_prefix="chore/bump",
    )


def test_pin_freshness_workflow_invokes_composite_action() -> None:
    """`reusable-pin-freshness.yml` invokes the composite Action exactly once."""
    _assert_workflow_invokes_composite(
        workflow_path=_FRESHNESS_WORKFLOW_PATH,
        expected_branch_prefix="chore/freshness-bump",
    )


# ---------------------------------------------------------------------------
# Duplication-removal regression guard
# ---------------------------------------------------------------------------


def _assert_case_block_extracted(*, workflow_path: Path) -> None:
    """Assert the rewrite case-block over the four pin formats is not inlined in a workflow."""
    text = _read(path=workflow_path)
    for fmt in _PIN_FORMAT_CASE_ARMS:
        assert fmt not in text, (
            f"{workflow_path.name} still inlines the case-arm {fmt!r}; "
            f"the li-b4yiuv extraction did not remove the duplication"
        )


def test_pin_rewrite_case_block_extracted_from_bump_dispatch() -> None:
    """The case-block is gone from `reusable-bump-pin-from-dispatch.yml`."""
    _assert_case_block_extracted(workflow_path=_BUMP_WORKFLOW_PATH)


def test_pin_rewrite_case_block_extracted_from_pin_freshness() -> None:
    """The case-block is gone from `reusable-pin-freshness.yml`."""
    _assert_case_block_extracted(workflow_path=_FRESHNESS_WORKFLOW_PATH)


def test_pin_rewrite_case_block_lives_in_composite_action() -> None:
    """The case-block over the four pin formats lives in the composite Action."""
    text = _read(path=_ACTION_PATH)
    for fmt in _PIN_FORMAT_CASE_ARMS:
        assert fmt in text, (
            f"composite Action missing case-arm for {fmt!r}; "
            f"the rewrite step body was not preserved during extraction"
        )


# ---------------------------------------------------------------------------
# Stray-gitlink footgun guard (livespec-dev-tooling-8ml)
# ---------------------------------------------------------------------------


def _commit_step_body(*, text: str) -> str:
    """Return the body of the `Commit + push bump branch` step.

    The slice runs from that step's `name:` line to the next top-level
    step (` - name:`) or end-of-file, so the assertions below cannot be
    satisfied by matching lines elsewhere in the Action.
    """
    match = re.search(
        r"^    - name: Commit \+ push bump branch\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, "composite Action missing the `Commit + push bump branch` step"
    return match.group(0)


def _command_pos(*, body: str, command: str) -> int:
    """Return the offset of an actual command line in the step body.

    Matches the command only when it begins a line at the script's 8-space
    indentation, so a backtick mention of the same command inside a `#`
    comment cannot be mistaken for the command itself.
    """
    match = re.search(rf"^        {re.escape(command)}\b", body, re.MULTILINE)
    return match.start() if match else -1


def test_commit_step_excludes_support_module_checkout() -> None:
    """The commit step excludes the nested support-module checkout before `git add -A`.

    Per livespec-dev-tooling-8ml: a local `info/exclude` entry for
    `./.livespec-dev-tooling` MUST precede the `git add -A` so the nested
    checkout can never be staged as a stray gitlink.
    """
    body = _commit_step_body(text=_read(path=_ACTION_PATH))
    exclude_pos = body.find(_GITLINK_EXCLUDE_ENTRY)
    assert exclude_pos != -1, (
        "commit step does not exclude the support-module checkout "
        f"({_GITLINK_EXCLUDE_ENTRY!r}); a blind `git add -A` would stage it "
        "as a stray gitlink"
    )
    assert _GITLINK_EXCLUDE_TARGET in body, (
        "commit step exclude must write to the git dir's "
        f"{_GITLINK_EXCLUDE_TARGET!r} (ephemeral, never committed)"
    )
    add_pos = _command_pos(body=body, command="git add -A")
    assert add_pos != -1, "commit step no longer runs `git add -A`"
    assert exclude_pos < add_pos, (
        "the support-module exclude MUST precede `git add -A` so the nested "
        "checkout is never staged"
    )


def test_commit_step_guards_against_staged_gitlink() -> None:
    """The commit step refuses to commit any staged gitlink (mode 160000).

    Per livespec-dev-tooling-8ml: defense-in-depth — the family uses no
    submodules, so a staged gitlink can only be a stray nested-checkout
    footgun. The guard MUST sit after `git add -A` and before `git commit`,
    matching on mode 160000 and exiting non-zero.
    """
    body = _commit_step_body(text=_read(path=_ACTION_PATH))
    guard_pos = body.find(_GITLINK_GUARD_GREP)
    assert guard_pos != -1, (
        "commit step has no guard refusing a staged gitlink "
        f"(expected an anchored {_GITLINK_GUARD_GREP!r} mode-{_GITLINK_GUARD_MODE} match)"
    )
    add_pos = _command_pos(body=body, command="git add -A")
    commit_pos = _command_pos(body=body, command="git commit")
    assert add_pos != -1 and commit_pos != -1, "commit step shape changed unexpectedly"
    assert add_pos < guard_pos < commit_pos, (
        f"the mode-{_GITLINK_GUARD_MODE} guard MUST sit after `git add -A` "
        "and before `git commit`"
    )
