"""Stale-base refresh of an open bump PR: composite Action and workflow wiring.

Per `SPECIFICATION/contracts.md` section "Cross-repo coordination automation
surface" (the "Stale-base refresh" clause), a bump PR whose branch is behind the
consumer's default branch is refreshed: the branch is reset to the default tip,
the same pin rewrite for that (source_repo, tag) is re-run, and the result is
pushed with `--force-with-lease` against the head that was read. A PR that is
current, and whose rewrite changes nothing, is left alone.

The behaviour lives in `.github/actions/bump-pin-refresh/action.yml` (plus the
refresh mode of `.github/actions/bump-pin-rewrite/action.yml`). The tests here
EXECUTE the composite's real step bodies, extracted by step name, against a
local bare repository standing in for `origin`. `uv` is replaced by a stub that
runs the repository's own modules with the current interpreter, so
autodiscovery, staleness comparison and the pin rewrite are the real code. The
one scenario that motivated the work (livespec-dev-tooling-m5cpnl) is replayed
end to end: the default branch gains a new pin-bearing line at the OLD tag after
the bump commit, and the refreshed branch head names the TARGET tag everywhere.

The workflow wiring (the push-triggered refresh jobs and the sweep backstop) is
asserted statically against the YAML text.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFRESH_ACTION = _REPO_ROOT / ".github" / "actions" / "bump-pin-refresh" / "action.yml"
_REWRITE_ACTION = _REPO_ROOT / ".github" / "actions" / "bump-pin-rewrite" / "action.yml"
_DISPATCH_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "reusable-bump-pin-from-dispatch.yml"
_FRESHNESS_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "reusable-pin-freshness.yml"

_SOURCE_REPO = "livespec-dev-tooling"
_OLD_TAG = "v1.0.0"
_NEW_TAG = "v2.0.0"
_BRANCH = f"chore/bump-{_SOURCE_REPO}-{_NEW_TAG}"
_PIN_KEY_PREFIX = "livespec-ai/livespec-dev-tooling/.github/workflows/reusable-x.yml"
_RUN_INDENT = 8

_GIT_ENV_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

# A `uv` stand-in: `uv run --project <dir> python -m <module>` runs the module
# from THIS repository's source with the test interpreter.
_UV_STUB = """#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == "run" ]] && shift
[[ "$1" == "--project" ]] && shift 2
[[ "$1" == "python" ]] && shift
exec "$STUB_PYTHON" "$@"
"""

# The Job image carries no `jq`, so the steps' three trivial filters (`.[]`,
# `.[].k`, `.k`, with -r / -c) run through this stand-in instead of making the
# tests depend on a host binary.
_JQ_STUB = """#!/usr/bin/env python3
import json
import sys

raw = "-r" in sys.argv
expr = [a for a in sys.argv[1:] if not a.startswith("-")][0]
data = json.load(sys.stdin)
items = data if expr.startswith(".[]") else [data]
field = expr.removeprefix(".[]").removeprefix(".")
for item in items:
    value = item[field] if field else item
    if raw and isinstance(value, str):
        print(value)
    else:
        print(json.dumps(value, separators=(",", ":")))
"""


def _read(*, path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _step_script(*, text: str, name: str) -> str:
    """Return the `run:` block of the step called `name` as a bash script."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {name}")
    run_at = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body: list[str] = []
    for line in lines[run_at + 1 :]:
        if line.strip() == "":
            body.append("")
            continue
        if len(line) - len(line.lstrip(" ")) < _RUN_INDENT:
            break
        body.append(line[_RUN_INDENT:])
    return "\n".join(body) + "\n"


def _step_block(*, text: str, name: str) -> str:
    """Return the full YAML text of the step called `name`."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {name}")
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("    - name:"):
            end = i
            break
    return "\n".join(lines[start:end])


def _env(*, tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    for var in _GIT_ENV_VARS:
        _ = env.pop(var, None)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    uv = bin_dir / "uv"
    _ = uv.write_text(_UV_STUB, encoding="utf-8")
    uv.chmod(0o755)
    jq = bin_dir / "jq"
    _ = jq.write_text(_JQ_STUB, encoding="utf-8")
    jq.chmod(0o755)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["STUB_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(_REPO_ROOT)
    return env


def _git(*, args: list[str], cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, check=True, capture_output=True, text=True
    )
    return result.stdout


def _write_pin(*, work: Path, name: str, tag: str) -> None:
    workflows = work / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    _ = (workflows / name).write_text(
        f"jobs:\n  j:\n    uses: {_PIN_KEY_PREFIX}@{tag}\n", encoding="utf-8"
    )


def _commit(*, work: Path, env: dict[str, str], message: str) -> None:
    _git(args=["add", "-A"], cwd=work, env=env)
    _git(args=["commit", "--quiet", "-m", message], cwd=work, env=env)


def _sandbox(*, tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """A bare origin, a work clone on master, and one pin at the OLD tag."""
    env = _env(tmp_path=tmp_path)
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _git(args=["init", "--quiet", "--bare", "--initial-branch=master", "."], cwd=origin, env=env)
    work = tmp_path / "work"
    work.mkdir()
    _git(args=["init", "--quiet", "--initial-branch=master", "."], cwd=work, env=env)
    _git(args=["config", "user.name", "livespec-pr-bot[bot]"], cwd=work, env=env)
    _git(args=["config", "user.email", "bot@example.invalid"], cwd=work, env=env)
    _write_pin(work=work, name="a.yml", tag=_OLD_TAG)
    _commit(work=work, env=env, message="base")
    _git(args=["remote", "add", "origin", str(origin)], cwd=work, env=env)
    _git(args=["push", "--quiet", "origin", "master"], cwd=work, env=env)
    return origin, work, env


def _open_bump_branch(*, work: Path, env: dict[str, str]) -> str:
    """Push the bump branch (a.yml at the NEW tag) off master; return its head."""
    _git(args=["checkout", "--quiet", "-b", _BRANCH], cwd=work, env=env)
    _write_pin(work=work, name="a.yml", tag=_NEW_TAG)
    _commit(work=work, env=env, message=f"chore(deps): bump {_SOURCE_REPO} pin to {_NEW_TAG}")
    _git(args=["push", "--quiet", "origin", _BRANCH], cwd=work, env=env)
    head = _git(args=["rev-parse", "HEAD"], cwd=work, env=env).strip()
    _git(args=["checkout", "--quiet", "master"], cwd=work, env=env)
    return head


def _master_gains_old_tag_pin(*, work: Path, env: dict[str, str]) -> None:
    """The default branch gains a NEW pin-bearing line at the OLD tag."""
    _write_pin(work=work, name="b.yml", tag=_OLD_TAG)
    _commit(work=work, env=env, message="feat: add a new pinned workflow")
    _git(args=["push", "--quiet", "origin", "master"], cwd=work, env=env)


def _run_step(
    *,
    tmp_path: Path,
    work: Path,
    env: dict[str, str],
    script: str,
    extra: dict[str, str],
) -> tuple[subprocess.CompletedProcess[str], str]:
    script_path = tmp_path / "step.sh"
    _ = script_path.write_text(script, encoding="utf-8")
    output = tmp_path / "github-output"
    _ = output.write_text("", encoding="utf-8")
    step_env = dict(env)
    step_env.update(extra)
    step_env["GITHUB_OUTPUT"] = str(output)
    completed = subprocess.run(
        ["bash", str(script_path)],
        cwd=str(work),
        env=step_env,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, output.read_text(encoding="utf-8")


def _decide(
    *, tmp_path: Path, work: Path, env: dict[str, str], branch: str = _BRANCH
) -> tuple[subprocess.CompletedProcess[str], str]:
    script = _step_script(
        text=_read(path=_REFRESH_ACTION),
        name="Read bump branch head and decide whether it needs a refresh",
    )
    return _run_step(
        tmp_path=tmp_path,
        work=work,
        env=env,
        script=script,
        extra={"SOURCE_REPO": _SOURCE_REPO, "TAG": _NEW_TAG, "BRANCH": branch},
    )


def _output_value(*, output: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.*)$", output, re.MULTILINE)
    assert match is not None, f"no `{key}=` line in step output:\n{output}"
    return match.group(1)


def test_refresh_decision_leaves_a_current_branch_alone(tmp_path: Path) -> None:
    """A branch not behind the default branch, carrying no stale pin, is not refreshed."""
    _, work, env = _sandbox(tmp_path=tmp_path)
    head = _open_bump_branch(work=work, env=env)

    completed, output = _decide(tmp_path=tmp_path, work=work, env=env)

    assert completed.returncode == 0, completed.stderr
    assert _output_value(output=output, key="needs_refresh") == "false"
    assert _output_value(output=output, key="behind") == "false"
    assert _output_value(output=output, key="head_sha") == head


def test_refresh_decision_flags_a_branch_behind_the_default_branch(tmp_path: Path) -> None:
    """A branch whose base moved on is behind and needs a refresh."""
    _, work, env = _sandbox(tmp_path=tmp_path)
    head = _open_bump_branch(work=work, env=env)
    _master_gains_old_tag_pin(work=work, env=env)

    completed, output = _decide(tmp_path=tmp_path, work=work, env=env)

    assert completed.returncode == 0, completed.stderr
    assert _output_value(output=output, key="needs_refresh") == "true"
    assert _output_value(output=output, key="behind") == "true"
    assert _output_value(output=output, key="default_branch") == "master"
    assert _output_value(output=output, key="head_sha") == head


def test_refresh_decision_flags_a_current_branch_whose_head_carries_a_stale_pin(
    tmp_path: Path,
) -> None:
    """The sweep backstop: not behind, but a head pin does not name the PR's tag."""
    _, work, env = _sandbox(tmp_path=tmp_path)
    _git(args=["checkout", "--quiet", "-b", _BRANCH], cwd=work, env=env)
    _write_pin(work=work, name="b.yml", tag=_OLD_TAG)
    _commit(work=work, env=env, message="a branch whose head still names the old tag")
    _git(args=["push", "--quiet", "origin", _BRANCH], cwd=work, env=env)
    _git(args=["checkout", "--quiet", "master"], cwd=work, env=env)

    completed, output = _decide(tmp_path=tmp_path, work=work, env=env)

    assert completed.returncode == 0, completed.stderr
    assert _output_value(output=output, key="behind") == "false"
    assert _output_value(output=output, key="head_stale") == "true"
    assert _output_value(output=output, key="needs_refresh") == "true"


def test_refresh_decision_refuses_a_branch_the_automation_does_not_own(tmp_path: Path) -> None:
    """The refresh MUST NOT touch a branch the bump automation does not own."""
    _, work, env = _sandbox(tmp_path=tmp_path)

    completed, _ = _decide(tmp_path=tmp_path, work=work, env=env, branch="feature/someone-else")

    assert completed.returncode != 0
    assert "not a bump-automation-owned branch" in completed.stdout + completed.stderr


def test_refresh_replays_the_stale_base_scenario_end_to_end(tmp_path: Path) -> None:
    """The default branch gains an old-tag pin after the bump commit; the refresh fixes it.

    Per livespec-dev-tooling-m5cpnl: refreshing the open bump PR branch for the
    target tag leaves the newly added pin-bearing line naming the target tag,
    and no pin-bearing line on the refreshed head names the old tag. The push is
    a `--force-with-lease` against the head that was read.
    """
    origin, work, env = _sandbox(tmp_path=tmp_path)
    head = _open_bump_branch(work=work, env=env)
    _master_gains_old_tag_pin(work=work, env=env)
    master_tip = _git(args=["rev-parse", "master"], cwd=work, env=env).strip()

    _, decide_output = _decide(tmp_path=tmp_path, work=work, env=env)
    assert _output_value(output=decide_output, key="needs_refresh") == "true"

    refresh_text = _read(path=_REFRESH_ACTION)
    reset_completed, reset_output = _run_step(
        tmp_path=tmp_path,
        work=work,
        env=env,
        script=_step_script(
            text=refresh_text, name="Reset to the default branch tip and re-run pin autodiscovery"
        ),
        extra={"SOURCE_REPO": _SOURCE_REPO, "BRANCH": _BRANCH, "DEFAULT_BRANCH": "master"},
    )
    assert reset_completed.returncode == 0, reset_completed.stderr
    records = reset_output.split("records<<JSONEOF\n", 1)[1].rsplit("\nJSONEOF", 1)[0]

    rewrite_text = _read(path=_REWRITE_ACTION)
    rewrite_completed, _ = _run_step(
        tmp_path=tmp_path,
        work=work,
        env=env,
        script=_step_script(text=rewrite_text, name="Rewrite matching pins to new tag"),
        extra={"TAG": _NEW_TAG, "RECORDS": records},
    )
    assert rewrite_completed.returncode == 0, rewrite_completed.stderr

    commit_completed, commit_output = _run_step(
        tmp_path=tmp_path,
        work=work,
        env=env,
        script=_step_script(text=rewrite_text, name="Commit + push bump branch"),
        extra={
            "SOURCE_REPO": _SOURCE_REPO,
            "TAG": _NEW_TAG,
            "BRANCH": _BRANCH,
            "REFRESH_BRANCH": _BRANCH,
            "REFRESH_EXPECTED_HEAD": head,
        },
    )
    assert commit_completed.returncode == 0, commit_completed.stderr
    assert _output_value(output=commit_output, key="changed") == "true"

    refreshed = _git(args=["rev-parse", _BRANCH], cwd=origin, env=env).strip()
    assert refreshed != head
    assert _git(args=["rev-parse", f"{refreshed}^"], cwd=origin, env=env).strip() == master_tip
    for name in ("a.yml", "b.yml"):
        pinned = _git(args=["show", f"{_BRANCH}:.github/workflows/{name}"], cwd=origin, env=env)
        assert f"@{_NEW_TAG}" in pinned, f"{name} MUST name the target tag on the refreshed head"
        assert f"@{_OLD_TAG}" not in pinned, f"{name} MUST NOT name the old tag"


def test_refresh_push_does_not_overwrite_a_concurrent_push(tmp_path: Path) -> None:
    """The lease names the head that was read, so a later push to the branch is not clobbered."""
    origin, work, env = _sandbox(tmp_path=tmp_path)
    head = _open_bump_branch(work=work, env=env)
    _git(args=["checkout", "--quiet", "-b", "other", _BRANCH], cwd=work, env=env)
    _ = (work / "concurrent.txt").write_text("landed after the read\n", encoding="utf-8")
    _commit(work=work, env=env, message="a concurrent push to the bump branch")
    _git(args=["push", "--quiet", "origin", f"other:{_BRANCH}"], cwd=work, env=env)
    concurrent = _git(args=["rev-parse", "other"], cwd=work, env=env).strip()
    _git(args=["checkout", "--quiet", "-B", _BRANCH, "master"], cwd=work, env=env)
    _write_pin(work=work, name="a.yml", tag=_NEW_TAG)

    completed, _ = _run_step(
        tmp_path=tmp_path,
        work=work,
        env=env,
        script=_step_script(text=_read(path=_REWRITE_ACTION), name="Commit + push bump branch"),
        extra={
            "SOURCE_REPO": _SOURCE_REPO,
            "TAG": _NEW_TAG,
            "BRANCH": _BRANCH,
            "REFRESH_BRANCH": _BRANCH,
            "REFRESH_EXPECTED_HEAD": head,
        },
    )

    assert completed.returncode != 0
    assert _git(args=["rev-parse", _BRANCH], cwd=origin, env=env).strip() == concurrent


def test_refresh_steps_after_the_decision_run_only_when_a_refresh_is_needed() -> None:
    """A current branch pushes nothing: every mutating step is gated on the decision."""
    text = _read(path=_REFRESH_ACTION)
    for name in (
        "Reset to the default branch tip and re-run pin autodiscovery",
        "Re-run the pin rewrite on the reset branch and push with a lease",
    ):
        assert "steps.decide.outputs.needs_refresh == 'true'" in _step_block(text=text, name=name)


def test_rewrite_action_opens_no_pr_in_refresh_mode() -> None:
    """Refresh mode pushes the existing branch; a PR is already open for it."""
    text = _read(path=_REWRITE_ACTION)
    block = _step_block(text=text, name="Open auto-merge PR")
    assert "inputs.refresh_branch == ''" in block


def test_dispatch_workflow_refreshes_open_bump_prs_when_there_is_no_release_payload() -> None:
    """A push to the default branch carries no source_repo; it refreshes instead of opening."""
    text = _read(path=_DISPATCH_WORKFLOW)
    assert "        if: ${{ inputs.source_repo != '' }}" in text
    assert "        if: ${{ inputs.source_repo == '' }}" in text
    assert "  refresh-open-bump:" in text
    assert "uses: ./.livespec-dev-tooling/.github/actions/bump-pin-refresh" in text


def test_freshness_workflow_refreshes_stale_open_bump_prs_each_sweep() -> None:
    """The sweep backstop refreshes every open bump PR through the same composite."""
    text = _read(path=_FRESHNESS_WORKFLOW)
    assert "  plan-refresh:" in text
    assert "  refresh-open-bump:" in text
    assert "uses: ./.livespec-dev-tooling/.github/actions/bump-pin-refresh" in text


def test_conditional_jobs_never_skip_by_job_level_condition() -> None:
    """A no-op reports success through an early-exit step, never a by-condition skip.

    A matrix job whose job-level `if` is false is skipped before the matrix expands, so GitHub
    reports a skipped check named with the unrendered template, which the release-currency
    grader reads as not green (livespec-dev-tooling-kefuik).
    """
    for path, jobs in (
        (_DISPATCH_WORKFLOW, ("bump-pin", "plan-refresh", "refresh-open-bump")),
        (_FRESHNESS_WORKFLOW, ("open-bump-pr", "refresh-open-bump")),
    ):
        text = _read(path=path)
        for job in jobs:
            block = text.split(f"\n  {job}:\n", 1)[1].split("\n    steps:\n", 1)[0]
            assert "\n    if:" not in block, f"{job} still skips by job-level condition"
