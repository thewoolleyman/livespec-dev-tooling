"""Fixture test for the `bump-pin-rewrite` composite Action invocation surface.

Per `SPECIFICATION/contracts.md` section "Composite Actions wire contract"
and section "Cross-repo coordination automation surface", the
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

# Three of the `pin_format` case-arm values the rewrite step dispatches
# on, per SPECIFICATION/contracts.md section "Pin autodiscovery rules" — this
# regression guard checks they were extracted out of the reusable
# workflows into the composite Action.
_PIN_FORMAT_CASE_ARMS = (
    "livespec_jsonc_compat_pinned)",
    "pyproject_toml_uv_sources)",
    "vendor_jsonc)",
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


def test_pin_freshness_composite_invocation_carries_the_bump_step_id() -> None:
    """The composite invocation is addressable, so later steps can gate on its outputs.

    Without an `id`, `steps.bump.outputs.changed` resolves to the empty string
    and every gate keyed on it silently evaluates false — the codex-acp gate
    would then NEVER dispatch rather than dispatch conditionally.
    """
    text = _read(path=_FRESHNESS_WORKFLOW_PATH)
    assert "\n        id: bump\n" in text, (
        "the composite invocation in reusable-pin-freshness.yml must carry `id: bump` "
        "so the codex-acp gate steps can gate on its `changed` output"
    )


def test_codex_acp_gate_steps_are_gated_on_the_bump_changed_output() -> None:
    """Both codex-acp gate steps skip on the composite's no-op path.

    On that path the composite pushes no branch and opens no PR
    (livespec-dev-tooling-bmf), so the dispatch step's `gh pr view "$BRANCH"`
    lookup would fail under `set -euo pipefail` and re-redden the sweep at a
    confusing point. Both the token-mint step and the dispatch step it feeds
    must carry the guard — gating only the dispatch would still mint an
    orchestrator-scoped token for a dispatch that never happens.
    """
    text = _read(path=_FRESHNESS_WORKFLOW_PATH)
    guarded = (
        "if: ${{ matrix.target.source_repo == 'agentclientprotocol/codex-acp'"
        " && steps.bump.outputs.changed == 'true' }}"
    )
    assert text.count(guarded) == 2, (
        "both codex-acp gate steps (the orchestrator-scoped token mint and the "
        "golden-master dispatch) must gate on `steps.bump.outputs.changed == 'true'`; "
        f"found {text.count(guarded)} of the 2 expected occurrences"
    )
    bare = "if: ${{ matrix.target.source_repo == 'agentclientprotocol/codex-acp' }}"
    assert bare not in text, (
        "an ungated codex-acp step remains — it would run on the composite's "
        "no-op path and fail looking up a PR that was never opened"
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
# Fabro docker pin: prefix-preserving rewrite via the tested module (livespec-3lev.4)
# ---------------------------------------------------------------------------

# Since the layered-image split, the fabro-sandbox pin carries a `<layer>-`
# prefix (`python-`/`python-rust-`) over the `vX.Y.Z` release. A bare-`$TAG`
# rewrite would drop that prefix and break the pin on the next release, so the
# `fabro_sandbox_docker_image` case dispatches the typed, unit-tested
# `fabro_image_pin_rewrite` module (behavioral coverage in
# `test_fabro_image_pin_rewrite.py`) instead of the inline heredoc that dropped
# the prefix.
_FABRO_PIN_REWRITE_MODULE = "livespec_dev_tooling.cross_repo.fabro_image_pin_rewrite"


def test_fabro_docker_pin_case_dispatches_prefix_preserving_module() -> None:
    """The `fabro_sandbox_docker_image` case dispatches the tested rewrite module.

    Per livespec-3lev.4: the fabro-sandbox pin now carries a `<layer>-` prefix,
    so the rewrite MUST preserve it. That logic lives in the typed, unit-tested
    `fabro_image_pin_rewrite` module (behavioral coverage in
    `test_fabro_image_pin_rewrite.py`), invoked here via `python -m` instead of
    an inline heredoc whose bare-`$TAG` rewrite silently dropped the prefix.
    """
    text = _read(path=_ACTION_PATH)
    assert (
        "fabro_sandbox_docker_image)" in text
    ), "composite Action missing the fabro_sandbox_docker_image case arm"
    assert f"python -m {_FABRO_PIN_REWRITE_MODULE}" in text, (
        f"the fabro_sandbox_docker_image case MUST dispatch the "
        f"{_FABRO_PIN_REWRITE_MODULE} module (not an inline heredoc that could "
        "drop the <layer>- prefix)"
    )
    assert "failed to rewrite docker image tag" not in text, (
        "the inline heredoc for the docker pin (with its prefix-dropping "
        "bare-$TAG rewrite) MUST be replaced by the module dispatch"
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

    Per livespec-dev-tooling-8ml: defense-in-depth — the fleet uses no
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


# ---------------------------------------------------------------------------
# Empty-staged-diff no-op guard (livespec-dev-tooling-bmf)
# ---------------------------------------------------------------------------

# Per livespec-dev-tooling-bmf: when the pin rewrite produces no change,
# `git add -A` stages nothing, `git commit` exits non-zero with "nothing to
# commit, working tree clean", and the step's `set -e` fails the whole run.
# That reports a NO-OP as a hard failure, leaving the fleet's only
# propagation backstop permanently red and its status uninformative. The
# step MUST detect the empty staged diff and finish cleanly instead.
#
# `git diff --cached --quiet` exits 0 exactly when nothing is staged, so it
# distinguishes "nothing to do" from "the commit failed". A `|| true` on the
# commit would NOT: it also swallows a genuine commit failure, converting
# this false positive into the false-NEGATIVE class already tracked as
# livespec-dev-tooling-ews (a stale pin silently never flagged).
_EMPTY_DIFF_CHECK = "git diff --cached --quiet"
# The commit step carries an `id:` so its outcome can gate the PR step.
_COMMIT_STEP_ID = "id: commit"
# The flag propagating "did we actually commit?" to the `Open auto-merge PR`
# step, which must NOT run with no branch pushed and no commit made.
_CHANGED_OUTPUT_FALSE = "changed=false"
_CHANGED_OUTPUT_TRUE = "changed=true"
_STEP_OUTPUT_SINK = "GITHUB_OUTPUT"
_PR_STEP_GATE = "steps.commit.outputs.changed == 'true'"


def _open_pr_step_body(*, text: str) -> str:
    """Return the body of the `Open auto-merge PR` step.

    Slices from that step's `name:` line to the next 4-space-indented step
    or end-of-file, mirroring `_commit_step_body`, so the assertions cannot
    be satisfied by lines elsewhere in the Action.
    """
    match = re.search(
        r"^    - name: Open auto-merge PR\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, "composite Action missing the `Open auto-merge PR` step"
    return match.group(0)


def test_commit_step_treats_an_empty_staged_diff_as_a_clean_no_op() -> None:
    """The commit step exits cleanly when the rewrite staged nothing.

    Per livespec-dev-tooling-bmf: the empty-staged-diff check MUST sit after
    `git add -A` and before `git commit`, and MUST record the outcome as a
    step output so the PR step can be gated on it.
    """
    body = _commit_step_body(text=_read(path=_ACTION_PATH))
    check_pos = body.find(_EMPTY_DIFF_CHECK)
    assert check_pos != -1, (
        "commit step has no empty-staged-diff check "
        f"(expected {_EMPTY_DIFF_CHECK!r}); a no-op rewrite still fails the "
        "step under `set -e` with 'nothing to commit, working tree clean'"
    )
    add_pos = _command_pos(body=body, command="git add -A")
    commit_pos = _command_pos(body=body, command="git commit")
    assert add_pos != -1 and commit_pos != -1, "commit step shape changed unexpectedly"
    assert add_pos < check_pos < commit_pos, (
        "the empty-staged-diff check MUST sit after `git add -A` (so it sees "
        "the staged set) and before `git commit` (so the no-op never reaches "
        "the failing commit)"
    )
    assert _COMMIT_STEP_ID in _read(path=_ACTION_PATH), (
        f"the commit step MUST carry {_COMMIT_STEP_ID!r} so the PR step can " "reference its output"
    )
    assert _STEP_OUTPUT_SINK in body, (
        "the commit step MUST record its outcome to $GITHUB_OUTPUT so the "
        "no-op state propagates to the PR step"
    )
    for flag in (_CHANGED_OUTPUT_FALSE, _CHANGED_OUTPUT_TRUE):
        assert flag in body, (
            f"the commit step MUST emit {flag!r} so both the no-op and the "
            "committed path are distinguishable downstream"
        )


def test_commit_step_does_not_swallow_a_genuine_commit_failure() -> None:
    """The commit itself is never suffixed with `|| true`.

    Per livespec-dev-tooling-bmf: swallowing the commit's exit status would
    also hide a REAL commit failure, converting this false positive into the
    false-negative class tracked as livespec-dev-tooling-ews. The no-op must
    be detected explicitly, before the commit, not masked after it.
    """
    body = _commit_step_body(text=_read(path=_ACTION_PATH))
    match = re.search(r"^        git commit\b.*$", body, re.MULTILINE)
    assert match, "commit step no longer runs `git commit`"
    commit_line = match.group(0)
    assert "||" not in commit_line, (
        "`git commit` MUST NOT be suffixed with `|| true` (or any `||` "
        "fallback): that swallows a genuine commit failure as well as the "
        f"no-op. Offending line: {commit_line!r}"
    )


def test_open_pr_step_is_gated_on_the_commit_step_change_flag() -> None:
    """The PR step is skipped when the commit step made no commit.

    Per livespec-dev-tooling-bmf: on the no-op path no branch is pushed and
    no commit exists, so `Open auto-merge PR` has nothing to open a PR from
    and MUST be skipped rather than run against a missing branch.
    """
    text = _read(path=_ACTION_PATH)
    body = _open_pr_step_body(text=text)
    assert _PR_STEP_GATE in body, (
        f"the `Open auto-merge PR` step MUST be gated on {_PR_STEP_GATE!r}; "
        "without it the step runs on the no-op path with no pushed branch"
    )
    gate_pos = body.find(_PR_STEP_GATE)
    run_pos = body.find("run: |")
    assert run_pos != -1 and gate_pos < run_pos, (
        "the gate MUST be a step-level `if:` condition, not a line inside the " "step's script"
    )


def test_composite_action_exports_the_change_flag_as_an_output() -> None:
    """The Action exports `changed` so callers can gate their own follow-up steps.

    Per livespec-dev-tooling-bmf: a caller with a step that depends on the
    bump PR existing (e.g. the codex-acp golden-master gate dispatch, which
    looks the PR up by branch name) needs to know whether this Action
    actually opened one.
    """
    text = _read(path=_ACTION_PATH)
    match = re.search(r"^outputs:\n.*?(?=^\w+:)", text, re.MULTILINE | re.DOTALL)
    assert match, "composite Action declares no top-level `outputs:` block"
    outputs_block = match.group(0)
    assert "changed:" in outputs_block, (
        "composite Action MUST export a `changed` output so callers can gate "
        "steps that require the bump PR to exist"
    )
    assert (
        "steps.commit.outputs.changed" in outputs_block
    ), "the `changed` output MUST take its value from the commit step's flag"


# ---------------------------------------------------------------------------
# uv.lock re-lock step (livespec-glv6)
# ---------------------------------------------------------------------------

# The composite Action MUST re-lock uv.lock AFTER rewriting the pin, else
# the committed lock lags the bumped pyproject pin by one release: the
# caller's pre-rewrite `uv sync` re-locks against the OLD tag and nothing
# re-locks afterward (livespec-glv6).
_RELOCK_STEP_NAME = "Refresh uv.lock for bumped pyproject pins"
# Only this pin format touches uv.lock, so the step selects these records.
_RELOCK_PIN_FORMAT = "pyproject_toml_uv_sources"
# `--refresh-package` defeats a stale uv git-ref cache that would otherwise
# re-resolve the just-pushed tag to the previously-cached ref.
_RELOCK_REFRESH_FLAG = "--refresh-package"
_TOOL_PIN_STEP_NAME = "Reconcile canonical tool pins"
_TOOL_PIN_SOURCE_REPO_GATE = "if: ${{ inputs.source_repo == 'livespec-dev-tooling' }}"
_RELEASE_TAG_REF = "refs/tags/${TAG}"
_TOOL_PIN_MODULE = "livespec_dev_tooling.cross_repo.tool_pin_projection"


def _relock_step_body(*, text: str) -> str:
    """Return the body of the `Refresh uv.lock for bumped pyproject pins` step.

    Slices from the step's `name:` line to the next 4-space-indented step
    or end-of-file, so assertions cannot be satisfied by lines elsewhere.
    """
    match = re.search(
        r"^    - name: Refresh uv\.lock for bumped pyproject pins\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"composite Action missing the {_RELOCK_STEP_NAME!r} step"
    return match.group(0)


def test_relock_step_refreshes_lock_before_commit() -> None:
    """The Action re-locks the bumped uv-sources package(s) before committing.

    Per livespec-glv6: the step selects `pyproject_toml_uv_sources` records
    (the only pin format that touches uv.lock) and runs
    `uv lock --refresh-package` for each, and MUST precede the
    `Commit + push bump branch` step so the refreshed lock is committed.
    """
    text = _read(path=_ACTION_PATH)
    body = _relock_step_body(text=text)
    assert _RELOCK_PIN_FORMAT in body, (
        f"the re-lock step must select {_RELOCK_PIN_FORMAT!r} records (the only "
        "pin format that touches uv.lock)"
    )
    assert (
        _command_pos(body=body, command="uv lock") != -1
    ), "the re-lock step no longer runs `uv lock`"
    assert _RELOCK_REFRESH_FLAG in body, (
        f"the re-lock step must pass {_RELOCK_REFRESH_FLAG!r} to defeat a stale " "uv git-ref cache"
    )
    relock_pos = text.find(_RELOCK_STEP_NAME)
    commit_pos = text.find("- name: Commit + push bump branch")
    assert relock_pos != -1 and commit_pos != -1, "composite Action step shape changed"
    assert relock_pos < commit_pos, (
        "the re-lock step MUST precede `Commit + push bump branch` so the "
        "refreshed uv.lock is committed alongside the rewritten pin"
    )


def test_relock_step_resyncs_the_consumer_venv_after_relocking() -> None:
    """The re-lock step also RE-SYNCS the consumer venv against the bumped pin.

    The calling reusable workflow syncs the consumer's environment BEFORE the
    pin rewrite, so without a re-sync here the venv holds the PRE-bump
    livespec-dev-tooling for the rest of the job. Every later step that resolves
    canonical data or runs a `just` recipe out of the consumer's OWN environment
    (the canonical-slug capture below, the canonical-slugs projection re-stamp)
    would then read the old version's answer while the committed pin says the
    new one.
    """
    body = _relock_step_body(text=_read(path=_ACTION_PATH))
    # `_command_pos` anchors on the script's 8-space indent, so the step's own
    # `#` comment — which mentions the caller's PRE-rewrite `uv sync` — cannot
    # be mistaken for the command itself.
    lock_pos = _command_pos(body=body, command="uv lock")
    sync_pos = _command_pos(body=body, command="uv sync --all-groups")
    assert sync_pos != -1, (
        "the re-lock step must re-sync the consumer venv (`uv sync --all-groups`) "
        "so the environment holds the version the bumped pin names"
    )
    assert (
        lock_pos != -1 and lock_pos < sync_pos
    ), "the re-sync must follow `uv lock`, not precede it"


def _tool_pin_step_body(*, text: str) -> str:
    """Return the body of the canonical tool-pin projection step."""
    match = re.search(
        r"^    - name: Reconcile canonical tool pins\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"composite Action missing the {_TOOL_PIN_STEP_NAME!r} step"
    return match.group(0)


def test_tool_pin_step_projects_shellcheck_pin_before_canonical_reconcile() -> None:
    """The Action projects tag-matched tool data before wiring the new check.

    The v1.18.4 fanout wired `check-shell-quality` into consumers, but left their
    `.mise.toml` without `shellcheck = "0.11.0"`. Those PRs then failed before
    corpus analysis because `run_shellcheck` reached version verification with
    no binary. The bump commit must project the tool pin in the same pre-commit
    fanout path as canonical justfile/CI wiring.
    """
    text = _read(path=_ACTION_PATH)
    body = _tool_pin_step_body(text=text)
    assert ".mise.toml" in body, "the tool-pin step must edit the consumer .mise.toml"
    assert (
        _TOOL_PIN_SOURCE_REPO_GATE in body
    ), "bumps for arbitrary source repos must not mutate consumer tool pins"
    assert "TAG: ${{ inputs.tag }}" in body
    assert (
        _RELEASE_TAG_REF in body
    ), "pin data must come from the source release, not a newer support checkout"
    assert "git -C .livespec-dev-tooling show FETCH_HEAD:.mise.toml" in body
    assert (
        _TOOL_PIN_MODULE in body
    ), "the composite must delegate projection to the typed/tested module"
    tool_pin_pos = text.find(_TOOL_PIN_STEP_NAME)
    check_reconcile_pos = text.find("- name: Reconcile canonical check wiring")
    assert tool_pin_pos != -1 and check_reconcile_pos != -1, "composite Action step shape changed"
    assert tool_pin_pos < check_reconcile_pos, (
        "the ShellCheck mise pin must be projected before canonical check wiring "
        "can add check-shell-quality to the consumer aggregate"
    )


def test_tool_pin_step_fails_closed_when_mise_toml_is_absent() -> None:
    """Consumers adopting check-shell-quality need a mise tool table to receive pins."""
    body = _tool_pin_step_body(text=_read(path=_ACTION_PATH))
    assert (
        '[[ ! -f "$mise_file" ]]' in body
    ), "the tool-pin step must explicitly test for a missing consumer .mise.toml"
    assert "::error::consumer .mise.toml not found" in body, (
        "missing .mise.toml must be a hard error, not a silent skip that opens "
        "a guaranteed-red bump PR"
    )


# ---------------------------------------------------------------------------
# Canonical check wiring reconcile step (fleet-check-coverage PR4 fallout)
# ---------------------------------------------------------------------------

# When a livespec-dev-tooling release adds a new module under
# `livespec_dev_tooling/checks/`, the live canonical-check set grows. Consumers
# that already run `check-aggregate-completeness` must have their `justfile`
# canonical block reconciled in the same bump PR, or the bump is guaranteed to
# fail before the new check can be adopted. The reconcile ALGORITHM lives in the
# typed, unit-tested `livespec_dev_tooling.cross_repo.justfile_canonical_reconcile`
# module (extracted from a former inline heredoc); this composite-Action step
# just reads the canonical set and dispatches that module, so the step-shape
# assertions below verify the WIRING (reads canonical_checks, invokes the
# reconcile module, precedes commit) — the reconcile behavior itself is covered
# by `tests/livespec_dev_tooling/cross_repo/test_justfile_canonical_reconcile.py`.
_RECONCILE_STEP_NAME = "Reconcile canonical check wiring"
_CANONICAL_CHECKS_MODULE = "livespec_dev_tooling.canonical_checks"
_RECONCILE_MODULE = "livespec_dev_tooling.cross_repo.justfile_canonical_reconcile"
# The ci.yml half of the same reconcile: check-ci-matrix-completeness requires
# CI to RUN every canonical slug the justfile aggregate WIRES, so the step that
# grows the aggregate must grow CI's matrix in the same commit.
_CI_MATRIX_STEP_NAME = "Reconcile canonical CI matrix wiring"
_CI_MATRIX_MODULE = "livespec_dev_tooling.cross_repo.ci_yaml_canonical_reconcile"
_SHELL_QUALITY_ASSERT_STEP_NAME = "Assert ShellCheck pin is gated"
_SHELL_QUALITY_GATE_MODULE = "livespec_dev_tooling.cross_repo.shellcheck_pin_gate"
_SHELL_QUALITY_SLUG = "check-shell-quality"
# The TOOL runs from the master support checkout (a consumer's pinned release
# predates the reconcile module); the canonical DATA must NOT. `.livespec-dev-tooling`
# is this repo at MASTER — ahead of every consumer pin — so resolving the
# filesystem-derived canonical slug set there injects slugs the consumer's PINNED
# aggregate-completeness gate does not recognize, reddening the bump PR by
# construction. The canonical capture therefore runs in the CONSUMER's environment.
_SUPPORT_CHECKOUT_PROJECT = "--project .livespec-dev-tooling"
_CANONICAL_CAPTURE = f"canonical_json=$(uv run python -m {_CANONICAL_CHECKS_MODULE} --json)"


def _reconcile_step_body(*, text: str) -> str:
    """Return the body of the canonical check wiring reconcile step."""
    match = re.search(
        r"^    - name: Reconcile canonical check wiring\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"composite Action missing the {_RECONCILE_STEP_NAME!r} step"
    return match.group(0)


def _ci_matrix_step_body(*, text: str) -> str:
    """Return the body of the canonical CI matrix wiring reconcile step."""
    match = re.search(
        r"^    - name: Reconcile canonical CI matrix wiring\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"composite Action missing the {_CI_MATRIX_STEP_NAME!r} step"
    return match.group(0)


def _shell_quality_assert_step_body(*, text: str) -> str:
    """Return the body of the ShellCheck-pin gating assertion step."""
    match = re.search(
        r"^    - name: Assert ShellCheck pin is gated\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"composite Action missing the {_SHELL_QUALITY_ASSERT_STEP_NAME!r} step"
    return match.group(0)


def test_reconcile_step_dispatches_reconcile_module_before_commit() -> None:
    """The Action reads the canonical set and dispatches the reconcile module before committing.

    The bump PR already updates the dev-tooling pin. If that pin introduces a
    new canonical check, the same commit must also reconcile the consumer's
    `justfile` wiring so `check-aggregate-completeness` can pass on the consumer
    PR. The step reads the canonical slug set from `canonical_checks` and hands
    it to the extracted reconcile module via `$CANONICAL_JSON`, before the
    commit step captures the result.
    """
    text = _read(path=_ACTION_PATH)
    body = _reconcile_step_body(text=text)
    assert (
        _CANONICAL_CHECKS_MODULE in body
    ), "the reconcile step must read the canonical slug set from `canonical_checks`"
    assert f"python -m {_RECONCILE_MODULE}" in body, (
        "the reconcile step must dispatch the extracted "
        "justfile_canonical_reconcile module (not an inline heredoc)"
    )
    assert 'CANONICAL_JSON="$canonical_json"' in body, (
        "the reconcile step must pass the captured canonical set to the module "
        "via the CANONICAL_JSON environment variable"
    )
    reconcile_pos = text.find(_RECONCILE_STEP_NAME)
    commit_pos = text.find("- name: Commit + push bump branch")
    assert reconcile_pos != -1 and commit_pos != -1, "composite Action step shape changed"
    assert reconcile_pos < commit_pos, (
        "the reconcile step MUST precede `Commit + push bump branch` so the "
        "consumer justfile wiring is committed with the pin bump"
    )


def test_canonical_slug_capture_resolves_from_the_consumer_not_the_support_checkout() -> None:
    """Both reconcile steps capture the canonical slug set from the CONSUMER's environment.

    The load-bearing version-skew fix. `canonical_check_slugs()` is a FILESYSTEM
    WALK of whatever `livespec_dev_tooling.checks` package is running, and the
    `.livespec-dev-tooling` support checkout is this repo at MASTER (the calling
    workflow checks it out with no `ref:`), which is ahead of every consumer's
    pin. Resolving the canonical set there injected slugs the consumer's PINNED
    `check-aggregate-completeness` did not recognize — they landed interleaved
    inside its canonical block (`out_of_order_canonical_slugs`) and reddened the
    bump PR by construction, deadlocking the fan-out.

    Capturing the set in the consumer's own environment makes the reconcile and
    the gate derive it from the SAME version, so they agree by construction at
    whatever the consumer pins. The reconcile MODULES keep `--project
    .livespec-dev-tooling` deliberately: they are the TOOL, not the DATA, and a
    consumer's pinned release predates them.
    """
    text = _read(path=_ACTION_PATH)
    for body in (_reconcile_step_body(text=text), _ci_matrix_step_body(text=text)):
        assert _CANONICAL_CAPTURE in body, (
            "the canonical slug set MUST be captured from the CONSUMER's environment "
            f"(plain `uv run`, no {_SUPPORT_CHECKOUT_PROJECT!r}) — resolving it from the "
            "master support checkout is the version skew that deadlocked the fan-out"
        )
        capture_line = next(
            line for line in body.splitlines() if _CANONICAL_CHECKS_MODULE in line and "$(" in line
        )
        assert (
            _SUPPORT_CHECKOUT_PROJECT not in capture_line
        ), "the canonical-slug capture must NOT run against the master support checkout"


def test_ci_matrix_reconcile_step_runs_after_the_justfile_reconcile_before_commit() -> None:
    """The ci.yml matrix reconcile follows the justfile reconcile and precedes the commit.

    `check-ci-matrix-completeness` asserts the canonical slugs CI RUNS are a
    SUPERSET of the canonical slugs the justfile `check:` aggregate WIRES. The
    justfile reconcile GROWS that aggregate — which is exactly what leaves the
    consumer's hand-maintained `strategy.matrix.target` list short the new
    entries. Reconciling the justfile alone therefore traded one guaranteed-red
    bump PR for another, on a different check with the same root cause; the
    matrix must be reconciled in the SAME commit.
    """
    text = _read(path=_ACTION_PATH)
    body = _ci_matrix_step_body(text=text)
    assert (
        f"python -m {_CI_MATRIX_MODULE}" in body
    ), "the CI matrix step must dispatch the ci_yaml_canonical_reconcile module"
    assert 'CANONICAL_JSON="$canonical_json"' in body, (
        "the CI matrix step must pass the captured canonical set to the module "
        "via the CANONICAL_JSON environment variable"
    )
    justfile_pos = text.find(_RECONCILE_STEP_NAME)
    ci_matrix_pos = text.find(_CI_MATRIX_STEP_NAME)
    commit_pos = text.find("- name: Commit + push bump branch")
    assert ci_matrix_pos != -1, "composite Action step shape changed"
    assert justfile_pos < ci_matrix_pos < commit_pos, (
        "the CI matrix reconcile MUST follow the justfile reconcile (whose newly-wired "
        "aggregate slugs it mirrors into CI) and precede `Commit + push bump branch` "
        "(so the reconciled ci.yml is committed with the pin bump)"
    )


def test_shellcheck_pin_requires_check_shell_quality_wiring_before_commit() -> None:
    """A ShellCheck pin must never be committed without its enforcing check wiring.

    Regression for livespec-dev-tooling-42t4az.3: sentinel-less consumers received
    the released `shellcheck` mise pin while both canonical reconcile steps skipped
    with notices, so the bump PR merged ungated. The action must fail closed after
    reconcile when the pin is present but the justfile aggregate, justfile recipe,
    or CI matrix/job does not carry `check-shell-quality`.
    """
    text = _read(path=_ACTION_PATH)
    body = _shell_quality_assert_step_body(text=text)
    assert _TOOL_PIN_SOURCE_REPO_GATE in body, (
        "only livespec-dev-tooling bumps project the ShellCheck tool pin, so only "
        "that source path must enforce the pin-with-wiring invariant"
    )
    assert f"python -m {_SHELL_QUALITY_GATE_MODULE}" in body, (
        "the invariant must dispatch the behavioral ShellCheck gate module, not "
        "an inline shell guard with only structural coverage"
    )
    assert "::notice::consumer does not carry check-aggregate-completeness" not in body, (
        "the regression was a sentinel-missing skip; this assertion must not repeat "
        "that notice-only gate"
    )
    ci_matrix_pos = text.find(_CI_MATRIX_STEP_NAME)
    assert_pos = text.find(_SHELL_QUALITY_ASSERT_STEP_NAME)
    commit_pos = text.find("- name: Commit + push bump branch")
    assert ci_matrix_pos < assert_pos < commit_pos, (
        "the ShellCheck invariant must run after canonical reconcile has had a chance "
        "to wire the check, and before the bump commit can capture an ungated pin"
    )


# ---------------------------------------------------------------------------
# Canonical-slugs projection re-stamp step (livespec-y9lb)
# ---------------------------------------------------------------------------

# When a bumped livespec-dev-tooling release adds a canonical check, the
# reconcile step above adds that slug to the consumer's justfile `check:`
# aggregate. A repo that ALSO carries the copier-template projection
# (`templates/orchestrator-plugin/canonical-slugs.yml`, regenerated by
# `just stamp-canonical-slugs`) must re-stamp it in the SAME bump commit, or
# the committed projection drifts and reddens master on
# `check-canonical-slugs-projection` / `check-copier-template-smoke`
# (observed on the v0.36.0 bump; livespec PR #1008). The re-stamp step is
# fail-soft (only the template-carrying repo exposes the recipe) and MUST
# delegate to the task runner rather than the underlying generator.
_RESTAMP_STEP_NAME = "Re-stamp canonical-slugs projection"
# The step MUST invoke the consumer's own stamp recipe via the task runner —
# the same generator its `check-canonical-slugs-projection` verifier runs, so
# the written projection and the verifier's expectation agree by construction.
# Line-anchored so a backtick mention of the same command inside the step's
# `#` comment cannot be mistaken for the actual invocation.
_RESTAMP_JUST_TARGET_RE = re.compile(r"^\s+just stamp-canonical-slugs\s*$", re.MULTILINE)
# Fail-soft guard: the recipe name is grepped out of the consumer justfile so
# non-template repos skip instead of erroring the bump job. This exact grep
# fragment appears only on the guard line, never in the surrounding comment.
_RESTAMP_RECIPE_GUARD = "grep -qE '^stamp-canonical-slugs:'"


def _restamp_step_body(*, text: str) -> str:
    """Return the body of the canonical-slugs projection re-stamp step."""
    match = re.search(
        r"^    - name: Re-stamp canonical-slugs projection\b.*?(?=^    - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"composite Action missing the {_RESTAMP_STEP_NAME!r} step"
    return match.group(0)


def test_restamp_step_runs_stamp_recipe_via_task_runner() -> None:
    """The Action re-stamps the projection via the consumer's own stamp recipe.

    Per livespec-y9lb: the re-stamp MUST invoke `just stamp-canonical-slugs`
    (the task runner, the single source of truth) rather than the underlying
    generator directly, so the written projection matches exactly what the
    consumer's `check-canonical-slugs-projection` verifier regenerates.
    """
    body = _restamp_step_body(text=_read(path=_ACTION_PATH))
    assert _RESTAMP_JUST_TARGET_RE.search(body), (
        "the re-stamp step must run `just stamp-canonical-slugs` (delegating "
        "to the task runner, not the generator directly)"
    )


def test_restamp_step_is_fail_soft_on_recipe_absence() -> None:
    """The re-stamp step guards on the stamp recipe's presence in the justfile.

    Per livespec-y9lb: only the copier-template-carrying repo exposes
    `stamp-canonical-slugs`; every other consumer MUST skip the re-stamp
    rather than erroring the bump job. The guard greps the consumer justfile
    for the recipe before invoking it.
    """
    body = _restamp_step_body(text=_read(path=_ACTION_PATH))
    guard_pos = body.find(_RESTAMP_RECIPE_GUARD)
    assert guard_pos != -1, (
        "the re-stamp step must guard on the stamp recipe's presence via "
        f"{_RESTAMP_RECIPE_GUARD!r} so non-template repos skip instead of "
        "failing the bump job"
    )
    invoke_match = _RESTAMP_JUST_TARGET_RE.search(body)
    assert invoke_match, "re-stamp step no longer runs `just stamp-canonical-slugs`"
    assert guard_pos < invoke_match.start(), (
        "the recipe-presence guard MUST precede the `just stamp-canonical-slugs` "
        "invocation so the recipe is only run where it exists"
    )


def test_restamp_step_between_reconcile_and_commit() -> None:
    """The re-stamp step runs after reconcile and before the commit step.

    Per livespec-y9lb: the projection is regenerated from the same canonical
    source the aggregate was just reconciled against, and the regenerated
    file must be staged by the commit step — so the re-stamp MUST sit after
    `Reconcile canonical check wiring` and before `Commit + push bump branch`.
    """
    text = _read(path=_ACTION_PATH)
    reconcile_pos = text.find(f"- name: {_RECONCILE_STEP_NAME}")
    restamp_pos = text.find(f"- name: {_RESTAMP_STEP_NAME}")
    commit_pos = text.find("- name: Commit + push bump branch")
    assert (
        reconcile_pos != -1 and restamp_pos != -1 and commit_pos != -1
    ), "composite Action step shape changed"
    assert reconcile_pos < restamp_pos < commit_pos, (
        "the re-stamp step MUST sit after `Reconcile canonical check wiring` "
        "and before `Commit + push bump branch` so the regenerated projection "
        "is staged with the pin bump"
    )


# ---------------------------------------------------------------------------
# Superseded bump PR close sweep (livespec-dev-tooling-5o6ssu)
# ---------------------------------------------------------------------------

_SUPERSESSION_MODULE = "livespec_dev_tooling.cross_repo.bump_pr_supersession"
_OPEN_PR_SWEEP_LIMIT = "--limit 100"


def test_superseded_bump_pr_sweep_fetches_more_than_the_default_pr_page() -> None:
    """The close sweep must inspect enough open bump PRs to cover accumulated fan-out backlogs."""
    text = _read(path=_ACTION_PATH)
    assert f"python -m {_SUPERSESSION_MODULE}" in text, (
        "the composite Action must dispatch the tested supersession classifier "
        "instead of embedding the decision logic in shell"
    )
    pr_list_match = re.search(
        r"^\s+open_prs=\$\(gh pr list (?P<args>[^\n]+)\)$",
        text,
        re.MULTILINE,
    )
    assert pr_list_match, "composite Action no longer captures open PRs for the supersession sweep"
    assert _OPEN_PR_SWEEP_LIMIT in pr_list_match.group("args"), (
        "the superseded-bump close sweep must pass `gh pr list --limit 100`; "
        "the default page can miss older superseded PRs in exactly the backlog "
        "this automation is meant to clear"
    )


# ---------------------------------------------------------------------------
# Stale-SHA rerun guard (livespec-dev-tooling-e37)
# ---------------------------------------------------------------------------

# The exact step name the guard declares in reusable-bump-pin-from-dispatch.yml.
_STALE_SHA_GUARD_STEP_NAME = "Stale-SHA rerun guard"
# The guard MUST condition on github.run_attempt to distinguish reruns.
_STALE_SHA_RUN_ATTEMPT = "run_attempt"
# The guard MUST query the live remote HEAD to see commits merged post-event.
_STALE_SHA_LS_REMOTE_CMD = "git ls-remote origin HEAD"
# The guard MUST compare against the event-pinned SHA (env-var source).
_STALE_SHA_EVENT_SHA_CTX = "github.sha"
# The guard's error MUST embed all four fresh-dispatch payload fields.
_STALE_SHA_EVENT_TYPE = "sibling-released"
_STALE_SHA_PAYLOAD_SOURCE_REPO = "client_payload[source_repo]"
_STALE_SHA_PAYLOAD_TAG = "client_payload[tag]"
_STALE_SHA_PAYLOAD_RELEASE_URL = "client_payload[release_url]"


def _stale_sha_guard_step_body(*, text: str) -> str:
    """Return the full body of the Stale-SHA rerun guard step.

    Slices from the step's `name:` line to the next 6-space-indented step
    or end-of-file, matching the indentation level of workflow job steps.
    """
    match = re.search(
        r"^      - name: Stale-SHA rerun guard\b.*?(?=^      - name: |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, "reusable-bump-pin-from-dispatch.yml missing the Stale-SHA rerun guard step"
    return match.group(0)


def test_stale_sha_guard_step_exists_in_bump_dispatch_workflow() -> None:
    """The Stale-SHA rerun guard step exists in reusable-bump-pin-from-dispatch.yml.

    Per SPECIFICATION/contracts.md section "Retry semantics (rerun vs fresh
    dispatch)": the workflow SHALL detect invalid reruns and fail fast.
    """
    text = _read(path=_BUMP_WORKFLOW_PATH)
    assert (
        _STALE_SHA_GUARD_STEP_NAME in text
    ), f"reusable-bump-pin-from-dispatch.yml missing the {_STALE_SHA_GUARD_STEP_NAME!r} step"


def test_stale_sha_guard_conditions_on_run_attempt() -> None:
    """The guard step's if: condition keys on github.run_attempt.

    A guard that fires on every run would refuse first-attempt runs;
    one that never checks run_attempt cannot distinguish reruns from
    first runs. The condition MUST reference run_attempt.
    """
    text = _read(path=_BUMP_WORKFLOW_PATH)
    body = _stale_sha_guard_step_body(text=text)
    assert _STALE_SHA_RUN_ATTEMPT in body, (
        "stale-SHA guard MUST reference github.run_attempt in its condition "
        "to detect reruns without blocking first-attempt runs"
    )


def test_stale_sha_guard_queries_live_remote_head() -> None:
    """The guard step queries the live remote HEAD via git ls-remote origin HEAD.

    A cached local ref (e.g. refs/remotes/origin/master) may reflect
    the stale checkout state rather than the true live HEAD. Only a
    direct ls-remote query surfaces commits merged after the event.
    """
    text = _read(path=_BUMP_WORKFLOW_PATH)
    body = _stale_sha_guard_step_body(text=text)
    assert _STALE_SHA_LS_REMOTE_CMD in body, (
        "stale-SHA guard MUST use 'git ls-remote origin HEAD' to query the "
        "live remote HEAD (not a cached local tracking ref)"
    )


def test_stale_sha_guard_compares_event_pinned_sha() -> None:
    """The guard step uses the event-pinned github.sha as the comparison baseline.

    The event-pinned SHA is the commit that triggered the original
    repository_dispatch; a rerun re-uses this SHA via actions/checkout.
    The guard compares the live HEAD against this pinned value.
    """
    text = _read(path=_BUMP_WORKFLOW_PATH)
    body = _stale_sha_guard_step_body(text=text)
    assert _STALE_SHA_EVENT_SHA_CTX in body, (
        "stale-SHA guard MUST reference github.sha (the event-pinned SHA) "
        "as the comparison baseline"
    )


def test_stale_sha_guard_embeds_fresh_dispatch_command() -> None:
    """The guard's error message embeds the exact fresh-dispatch command.

    Per SPECIFICATION/contracts.md section "Retry semantics": the actionable
    error MUST include event_type=sibling-released and all three
    client_payload fields so the operator can copy-paste the correct
    fresh-dispatch command.
    """
    text = _read(path=_BUMP_WORKFLOW_PATH)
    body = _stale_sha_guard_step_body(text=text)
    for fragment in (
        _STALE_SHA_EVENT_TYPE,
        _STALE_SHA_PAYLOAD_SOURCE_REPO,
        _STALE_SHA_PAYLOAD_TAG,
        _STALE_SHA_PAYLOAD_RELEASE_URL,
    ):
        assert fragment in body, (
            f"stale-SHA guard error MUST include {fragment!r} so the operator "
            "has the complete fresh-dispatch command"
        )


def test_stale_sha_guard_precedes_pin_autodiscovery() -> None:
    """The stale-SHA guard step appears before the Run pin-autodiscovery step.

    Per SPECIFICATION/contracts.md section "Retry semantics": fail fast — the
    guard MUST refuse before any substantive work so the rerun exits
    immediately without running autodiscovery, uv-sync, or pin-rewrites.
    """
    text = _read(path=_BUMP_WORKFLOW_PATH)
    guard_pos = text.find(f"- name: {_STALE_SHA_GUARD_STEP_NAME}")
    autodiscover_pos = text.find("- name: Run pin-autodiscovery")
    assert guard_pos != -1, "stale-SHA guard step not found in workflow"
    assert autodiscover_pos != -1, "pin-autodiscovery step not found in workflow"
    assert guard_pos < autodiscover_pos, (
        "stale-SHA guard MUST appear before pin-autodiscovery to fail fast "
        "before any substantive work"
    )
