"""§"Commit and merge discipline" — the refusal EXECUTED, and the strategy that preserves prefixes.

The section is one causal chain, not three independent rules: every commit on
`master` carries a Conventional Commits subject prefix, `release-please` reads
those prefixes to compute the next semver bump, direct commits to `master` are
forbidden, and the merge strategy MUST be rebase-merge "so each commit's subject
prefix lands intact on `master`". Break any link and the release version is
computed from commit subjects that are not the ones the authors wrote.

Two links have real, silent failure modes and neither is defended elsewhere:

- **The refusal is a shell body, not a check.** `00-no-commit-on-master` is
  inline shell in `lefthook.yml` — there is no module to unit-test and no
  aggregate member that runs it, so nothing in this repository has ever
  EXECUTED it. A body that stopped refusing (an inverted comparison, a dropped
  `exit 1`, a `$branch` typo that always compares empty) still parses, still
  runs on every commit, and still exits 0 — which reads exactly like a commit
  that was correctly allowed. So it is executed here against a `git` DOUBLE:
  once answering `master`, once answering a feature branch, and the exit codes
  are the assertion.

- **A merge strategy change is invisible until the next release.** Switching an
  automated merge from `--rebase` to `--squash` merges the pull request just
  fine. What it destroys is the per-commit subject prefixes: a branch carrying a
  `feat:` and three `fix:` commits collapses to one subject, so `release-please`
  computes its bump from that single line. The version is then wrong rather than
  missing, and the first evidence arrives at release time.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEFTHOOK = _REPO_ROOT / "lefthook.yml"
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_RELEASE_PLEASE_CONFIG = _REPO_ROOT / "release-please-config.json"

_MASTER_GUARD = "00-no-commit-on-master"
_PROTECTED_BRANCH = "master"

# The merge strategy the section mandates, and the two that discard prefixes.
_REQUIRED_STRATEGY = "--rebase"
_PREFIX_DESTROYING = ("--squash", "--merge")

# The prefixes `release-please` must be able to see in order to compute a bump.
_BUMP_BEARING_TYPES = ("feat", "fix")

_GUARD_BODY = re.compile(
    rf"^    {_MASTER_GUARD}:\n      run: \|\n(?P<body>(?:        .*\n|\n)+)",
    re.MULTILINE,
)
_MERGE_CALL = re.compile(r"^\s*(?:if\s+)?gh pr merge\b(?P<flags>.*)$", re.MULTILINE)


def _guard_body() -> str:
    """The inline shell `00-no-commit-on-master` runs, dedented to a runnable script."""
    matched = _GUARD_BODY.search(_LEFTHOOK.read_text(encoding="utf-8"))
    assert matched is not None, (
        f"`{_MASTER_GUARD}` must be a commit-msg command with an inline `run: |` body — "
        f"it is the mechanism the section names for forbidding direct commits to "
        f"`{_PROTECTED_BRANCH}`"
    )
    return "".join(line[8:] for line in matched.group("body").splitlines(keepends=True))


def _run_guard_on(*, branch: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Execute the guard body with a `git` double that answers `branch`."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    double = tmp_path / "git"
    double.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "{branch}"\n', encoding="utf-8")
    double.chmod(0o755)
    environment = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    return subprocess.run(
        ["bash", "-c", _guard_body()],
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env=environment,
        text=True,
    )


def test_the_master_guard_refuses_on_master_and_permits_a_feature_branch(tmp_path: Path) -> None:
    """The forbidding of direct commits to master, run rather than read."""
    refused = _run_guard_on(branch=_PROTECTED_BRANCH, tmp_path=tmp_path / "on-master")
    assert refused.returncode != 0, (
        f"the section forbids direct commits to `{_PROTECTED_BRANCH}` and names this hook "
        f"as the enforcement. Executed against a `git` answering `{_PROTECTED_BRANCH}`, "
        f"the body exited {refused.returncode} — a pass, which is indistinguishable from "
        f"a commit that was correctly allowed; stdout={refused.stdout!r} "
        f"stderr={refused.stderr!r}"
    )
    assert _PROTECTED_BRANCH in refused.stderr, (
        f"the refusal must say what it refused and why, on stderr where the committing "
        f"operator sees it; stderr={refused.stderr!r}"
    )

    permitted = _run_guard_on(branch="feature/some-work", tmp_path=tmp_path / "on-branch")
    assert permitted.returncode == 0, (
        f"the guard must refuse ONLY `{_PROTECTED_BRANCH}` — the section routes every "
        f"change through feature branches, so a guard that refuses those too blocks the "
        f"one path it is meant to permit; returncode={permitted.returncode} "
        f"stderr={permitted.stderr!r}"
    )


def test_every_automated_merge_requests_rebase_and_never_a_prefix_destroying_strategy() -> None:
    """ "Merge strategy MUST be rebase-merge so each commit's subject prefix lands intact"."""
    calls = [
        (path.name, matched.group("flags"))
        for path in sorted(_WORKFLOWS_DIR.glob("*.y*ml"))
        for matched in _MERGE_CALL.finditer(path.read_text(encoding="utf-8"))
    ]
    assert calls, (
        "this repository automates its merges, so at least one workflow must invoke "
        "`gh pr merge`; with none, this assertion would pass vacuously"
    )
    wrong = [
        f"{name}: gh pr merge{flags}"
        for name, flags in calls
        if _REQUIRED_STRATEGY not in flags
        or any(destroyer in flags for destroyer in _PREFIX_DESTROYING)
    ]
    assert not wrong, (
        f"every automated merge must request `{_REQUIRED_STRATEGY}`. A `--squash` or a "
        f"merge commit lands the branch just as successfully and collapses its per-commit "
        f"subjects into one, so `release-please` computes the next bump from a single "
        f"line instead of from the `feat:`/`fix:` prefixes the authors wrote — a WRONG "
        f"version rather than a missing one, first visible at release time; wrong={wrong}"
    )


def test_the_release_tool_is_configured_to_read_the_conventional_prefixes() -> None:
    """The prefix has a reader; without one the subject discipline decides nothing."""
    config = json.loads(_RELEASE_PLEASE_CONFIG.read_text(encoding="utf-8"))
    sections = config.get("changelog-sections", [])
    declared = {str(section.get("type", "")) for section in sections}
    missing = sorted(set(_BUMP_BEARING_TYPES) - declared)
    assert not missing, (
        f"the section makes `release-please` the READER of every subject prefix, so its "
        f"configuration must recognize the bump-bearing types; a type it does not know is "
        f"a commit whose prefix computes no bump at all; missing={missing} "
        f"declared={sorted(declared)}"
    )
