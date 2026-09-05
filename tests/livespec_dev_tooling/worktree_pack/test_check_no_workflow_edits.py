"""Behaviour tests for the pack member `worktree_pack/check-no-workflow-edits.sh`.

The seventh worktree-pack member is the fleet's ONE workflow-edit guard
(livespec-dev-tooling-fy02): an authorship control at the agent boundary
whose only override is HUMAN authorization — a tracked, per-change
declaration `.livespec-workflow-edit-exemption` that, when the repository
has a ledger, must name a work item carrying the human-set label
`approval:workflow-edit`. There is no environment escape of any kind.

Every case here builds a throwaway git repository with a bare `origin`
whose advertised default branch is `master` (so `refs/remotes/origin/HEAD`
resolves exactly as it does in a real clone), installs the canonical body
into `dev-tooling/` the way a consumer's `just check-no-workflow-edits`
recipe runs it, and asserts the exit code and the operator-facing message.
The ledger is never real: `bd` is a fake on a private `PATH` prefix that
records its argv and emits a scripted record, so no test touches the fleet
ledger or the network. The only subprocesses are `git` (fixture setup) and
`bash` (the script under test); `COVERAGE_PROCESS_START` / `COV_CORE_*`
are scrubbed from the child env so the guard's own `python3` label probe
never self-instruments under `pytest --cov`.

Exit-code contract under test: 0 pass, 1 a workflow edit without valid
human authorization, 2 the authorization could not be evaluated (ledger
unreachable, unparseable, or a malformed declaration) — fail closed.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import CANONICAL_NO_WORKFLOW_EDITS_BODY

__all__: list[str] = []

_GUARD_NAME = "check-no-workflow-edits.sh"
_DECLARATION = ".livespec-workflow-edit-exemption"
_WORKFLOW = Path(".github") / "workflows" / "ci.yml"
_WORK_ITEM = "livespec-dev-tooling-fy02"
_APPROVAL_LABEL = "approval:workflow-edit"

# git sets these in a hook's environment when it fires inside a worktree;
# under a lefthook pre-commit they leak in from the surrounding repo.
# Scrubbing them confines every git invocation to the tmp_path fixture.
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
# The guard's own inputs that the surrounding process must never leak in:
# the CI-venue marker and the bd override.
_GUARD_ENV_VARS: tuple[str, ...] = ("GITHUB_ACTIONS", "LIVESPEC_BD_PATH")


def _run_git(*, args: list[str], cwd: Path) -> None:
    """Run a git command in `cwd`, raising on failure."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _commit_all(*, repo: Path, message: str) -> None:
    _run_git(args=["add", "--all"], cwd=repo)
    _run_git(args=["commit", "--quiet", "-m", message], cwd=repo)


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _install_guard(*, repo: Path) -> None:
    """Materialize the canonical body under `dev-tooling/`, executable, as a consumer would."""
    script = repo / "dev-tooling" / _GUARD_NAME
    _write(path=script, text=CANONICAL_NO_WORKFLOW_EDITS_BODY)
    script.chmod(0o755)


def _init_repo_with_origin(*, tmp_path: Path, base_declaration: str | None = None) -> Path:
    """A clone on a feature branch whose `origin` advertises `master` as default.

    The base commit carries one workflow file. When `base_declaration` is
    given it is committed on the BASE too — the inherited-declaration case,
    where a declaration that exempted an earlier change must not exempt this
    one. The guard is installed into `dev-tooling/` (gitignored, exactly as
    the pack installer leaves it) before the feature branch is cut.
    """
    remote = tmp_path / "origin.git"
    remote.mkdir()
    _run_git(args=["init", "--bare", "--quiet", str(remote)], cwd=tmp_path)
    _run_git(args=["symbolic-ref", "HEAD", "refs/heads/master"], cwd=remote)

    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(args=["init", "--quiet", "--initial-branch=master"], cwd=repo)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)
    _write(path=repo / _WORKFLOW, text="name: ci\non: push\njobs: {}\n")
    _write(path=repo / "README.md", text="# fixture\n")
    _write(path=repo / ".gitignore", text="/dev-tooling/\n")
    if base_declaration is not None:
        _write(path=repo / _DECLARATION, text=base_declaration)
    _commit_all(repo=repo, message="base")
    _run_git(args=["remote", "add", "origin", str(remote)], cwd=repo)
    _run_git(args=["push", "--quiet", "-u", "origin", "master"], cwd=repo)
    _run_git(args=["remote", "set-head", "origin", "--auto"], cwd=repo)
    _run_git(args=["checkout", "--quiet", "-b", "feature/wip"], cwd=repo)
    _install_guard(repo=repo)
    return repo


def _edit_workflow(*, repo: Path, commit: bool) -> None:
    """Append one line to the workflow file; optionally commit it on the feature branch."""
    workflow = repo / _WORKFLOW
    _ = workflow.write_text(
        workflow.read_text(encoding="utf-8") + "# an agent edited this\n", encoding="utf-8"
    )
    if commit:
        _commit_all(repo=repo, message="edit workflow")


def _declaration_text(*, work_item: str = _WORK_ITEM, reason: str = "ratified fy02 edit") -> str:
    return f"work_item={work_item}\nreason={reason}\n"


def _declare(*, repo: Path, text: str, commit: bool) -> None:
    """Author the declaration in THIS branch — tracked (staged), optionally committed."""
    _write(path=repo / _DECLARATION, text=text)
    _run_git(args=["add", _DECLARATION], cwd=repo)
    if commit:
        _commit_all(repo=repo, message="declare workflow edit")


def _add_ledger_pointer(*, repo: Path) -> None:
    """Give the fixture a ledger: the `.beads/config.yaml` pointer the guard keys on."""
    _write(path=repo / ".beads" / "config.yaml", text="dolt:\n  host: 127.0.0.1\n  port: 3307\n")


def _fake_bd(
    *,
    fake_bin: Path,
    labels: list[str] | None = None,
    exit_code: int = 0,
    stdout: str | None = None,
) -> Path:
    """Install a scripted `bd` at `<fake_bin>/bd` that records its argv.

    Emits a one-record list carrying `labels` (the real `bd show --json`
    shape) unless `stdout` overrides the body verbatim, then exits
    `exit_code`. Returns the argv log path.
    """
    fake_bin.mkdir(parents=True, exist_ok=True)
    argv_log = fake_bin / "bd-argv.log"
    body = (
        stdout
        if stdout is not None
        else json.dumps([{"id": _WORK_ITEM, "status": "open", "labels": labels or []}])
    )
    body_file = fake_bin / "bd-stdout.txt"
    _ = body_file.write_text(body, encoding="utf-8")
    script = fake_bin / "bd"
    _ = script.write_text(
        "#!/usr/bin/env bash\n"
        f"printf '%s\\n' \"$*\" >> '{argv_log}'\n"
        f"cat '{body_file}'\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return argv_log


def _run_guard(
    *,
    repo: Path,
    path_prefix: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the installed guard from the repo root exactly as a consumer recipe does."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENV_VARS
        and key not in _GUARD_ENV_VARS
        and key != "COVERAGE_PROCESS_START"
        and not key.startswith("COV_CORE_")
    }
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    env.update(env_overrides or {})
    return subprocess.run(
        ["bash", f"dev-tooling/{_GUARD_NAME}"],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_canonical_body_carries_no_environment_escape() -> None:
    """The design's item (5): no env var of any kind changes the guard's verdict.

    The three retired escapes are named so a re-introduction under the old
    spelling is caught by name; the only environment reads the body may
    make are the CI-venue marker and the bd binary override.
    """
    for retired in ("LIVESPEC_WORKFLOW_EDIT_BASE", "LIVESPEC_FACTORY_BASE_REF", "SKIP_"):
        assert retired not in CANONICAL_NO_WORKFLOW_EDITS_BODY
    assert "set -euo pipefail" in CANONICAL_NO_WORKFLOW_EDITS_BODY
    assert CANONICAL_NO_WORKFLOW_EDITS_BODY.startswith("#!/usr/bin/env bash\n")


def test_no_workflow_change_passes_silently(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _write(path=repo / "src.txt", text="ordinary change\n")
    _commit_all(repo=repo, message="ordinary")

    completed = _run_guard(repo=repo)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""


def test_committed_workflow_edit_without_declaration_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workflow edit on the branch, no declaration: exit 1 naming the path and the human path."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 1, completed.stderr
    assert str(_WORKFLOW) in completed.stderr
    assert _DECLARATION in completed.stderr
    assert f"bd label add <ledger-id> {_APPROVAL_LABEL}" in completed.stderr


def test_unstaged_workflow_edit_without_declaration_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-commit moment: an uncommitted workflow edit is already in scope."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=False)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 1, completed.stderr
    assert str(_WORKFLOW) in completed.stderr


def test_untracked_workflow_file_without_declaration_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A brand-new, never-added workflow file is in scope too."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _write(path=repo / ".github" / "workflows" / "sneaky.yml", text="name: sneaky\n")

    completed = _run_guard(repo=repo)

    assert completed.returncode == 1, completed.stderr
    assert ".github/workflows/sneaky.yml" in completed.stderr


def test_declaration_inherited_from_base_is_not_an_authorization(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One exemption binds to one reviewed change: a base-inherited declaration exempts nothing."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path, base_declaration=_declaration_text())
    _edit_workflow(repo=repo, commit=True)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 1, completed.stderr
    assert "inherited" in completed.stderr
    assert str(_WORKFLOW) in completed.stderr


def test_untracked_declaration_is_not_an_authorization(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A declaration that is merely on disk (never `git add`ed) does not count."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _write(path=repo / _DECLARATION, text=_declaration_text())

    completed = _run_guard(repo=repo)

    assert completed.returncode == 1, completed.stderr
    assert "must be tracked" in completed.stderr


def test_valid_declaration_without_ledger_passes_with_the_no_ledger_note(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item (4c): no `.beads/config.yaml` → the tracked declaration alone authorizes, and says so."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 0, completed.stderr
    assert "no ledger" in completed.stderr
    assert _WORK_ITEM in completed.stderr


def test_staged_but_uncommitted_declaration_counts_as_authored_here(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-commit moment for the declaration itself: staged is authored in this change."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=False)
    _declare(repo=repo, text=_declaration_text(), commit=False)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 0, completed.stderr


def test_valid_declaration_with_ledger_and_approval_label_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item (4b): the declared work item carries the human-set label → pass, via `bd show <id> --json`."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)
    _add_ledger_pointer(repo=repo)
    fake_bin = tmp_path / "fakebin"
    argv_log = _fake_bd(fake_bin=fake_bin, labels=["origin:freeform", _APPROVAL_LABEL])

    completed = _run_guard(repo=repo, path_prefix=fake_bin)

    assert completed.returncode == 0, completed.stderr
    assert _APPROVAL_LABEL in completed.stderr
    assert argv_log.read_text(encoding="utf-8").splitlines() == [f"show {_WORK_ITEM} --json"]


def test_valid_declaration_with_ledger_but_no_approval_label_is_refused(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The declaration alone is not enough where a ledger exists: a human must set the label."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)
    _add_ledger_pointer(repo=repo)
    fake_bin = tmp_path / "fakebin"
    _ = _fake_bd(fake_bin=fake_bin, labels=["origin:freeform"])

    completed = _run_guard(repo=repo, path_prefix=fake_bin)

    assert completed.returncode == 1, completed.stderr
    assert f"bd label add {_WORK_ITEM} {_APPROVAL_LABEL}" in completed.stderr
    assert str(_WORKFLOW) in completed.stderr


def test_a_record_without_a_labels_key_is_an_absent_label(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`bd show --json` omits `labels` entirely on an unlabelled item; that is refusal, not exit 2."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)
    _add_ledger_pointer(repo=repo)
    fake_bin = tmp_path / "fakebin"
    _ = _fake_bd(fake_bin=fake_bin, stdout=json.dumps([{"id": _WORK_ITEM, "status": "open"}]))

    completed = _run_guard(repo=repo, path_prefix=fake_bin)

    assert completed.returncode == 1, completed.stderr


def test_failing_bd_fails_closed(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unreachable ledger is exit 2 — never a pass — naming the cause and the wrapper hint."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)
    _add_ledger_pointer(repo=repo)
    fake_bin = tmp_path / "fakebin"
    _ = _fake_bd(fake_bin=fake_bin, stdout="Error 1045 (28000): Access denied", exit_code=1)

    completed = _run_guard(repo=repo, path_prefix=fake_bin)

    assert completed.returncode == 2, completed.stderr
    assert "FAILING CLOSED" in completed.stderr
    assert "BEADS_DOLT_PASSWORD" in completed.stderr


def test_unparseable_bd_output_fails_closed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)
    _add_ledger_pointer(repo=repo)
    fake_bin = tmp_path / "fakebin"
    _ = _fake_bd(fake_bin=fake_bin, stdout="this is not json\n")

    completed = _run_guard(repo=repo, path_prefix=fake_bin)

    assert completed.returncode == 2, completed.stderr
    assert "not a ledger record" in completed.stderr


def test_livespec_bd_path_override_is_honoured(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`LIVESPEC_BD_PATH` names the bd binary, mirroring the package's own bd resolution."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)
    _add_ledger_pointer(repo=repo)
    fake_bin = tmp_path / "off-path"
    argv_log = _fake_bd(fake_bin=fake_bin, labels=[_APPROVAL_LABEL])

    completed = _run_guard(repo=repo, env_overrides={"LIVESPEC_BD_PATH": str(fake_bin / "bd")})

    assert completed.returncode == 0, completed.stderr
    assert argv_log.read_text(encoding="utf-8").splitlines() == [f"show {_WORK_ITEM} --json"]


def test_no_bd_binary_at_all_fails_closed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No bd override and no bd on PATH: the ledger cannot be consulted → exit 2, never a pass.

    `PATH` is rebuilt from the system directories so the host's real `bd`
    is out of reach while `git`, `bash`, `sed`, `sort` and `python3` stay
    resolvable.
    """
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=_declaration_text(), commit=True)
    _add_ledger_pointer(repo=repo)
    no_bd_path = os.pathsep.join(
        directory
        for directory in os.environ["PATH"].split(os.pathsep)
        if not (Path(directory) / "bd").exists()
    )

    completed = _run_guard(repo=repo, env_overrides={"PATH": no_bd_path})

    assert completed.returncode == 2, completed.stderr
    assert "no usable bd binary" in completed.stderr


def test_malformed_declaration_fails_closed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two `work_item=` lines: the declaration cannot be evaluated → exit 2 with the specific reason."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(
        repo=repo,
        text=f"work_item={_WORK_ITEM}\nwork_item=other-item\nreason=two ids\n",
        commit=True,
    )

    completed = _run_guard(repo=repo)

    assert completed.returncode == 2, completed.stderr
    assert "exactly one work_item= line" in completed.stderr


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (f"work_item={_WORK_ITEM}\n", "exactly one reason= line"),
        (f"work_item={_WORK_ITEM}\nreason=\n", "reason= must be non-empty"),
        ("work_item=two ids here\nreason=spaces\n", "single ledger id token"),
    ],
)
def test_each_declaration_rule_is_named_on_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, reason: str
) -> None:
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)
    _declare(repo=repo, text=text, commit=True)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 2, completed.stderr
    assert reason in completed.stderr


def test_github_actions_venue_is_skipped_with_a_note(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item (1): CI is not a venue — an unauthorized edit still exits 0 there, with one note."""
    monkeypatch.chdir(tmp_path)
    repo = _init_repo_with_origin(tmp_path=tmp_path)
    _edit_workflow(repo=repo, commit=True)

    completed = _run_guard(repo=repo, env_overrides={"GITHUB_ACTIONS": "true"})

    assert completed.returncode == 0, completed.stderr
    assert "not a CI venue" in completed.stderr
    assert completed.stderr.count("\n") == 1


def test_no_base_ref_passes_with_a_note(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Item (2): no origin/HEAD, origin/master, or origin/main → nothing to compare against."""
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "loner"
    repo.mkdir()
    _run_git(args=["init", "--quiet", "--initial-branch=master"], cwd=repo)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)
    _write(path=repo / _WORKFLOW, text="name: ci\n")
    _write(path=repo / ".gitignore", text="/dev-tooling/\n")
    _commit_all(repo=repo, message="base")
    _install_guard(repo=repo)
    _edit_workflow(repo=repo, commit=True)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 0, completed.stderr
    assert "no base to compare against" in completed.stderr


def test_origin_main_is_the_fallback_base_when_origin_head_is_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Item (2): an adopter whose default branch is `main` needs no override — the rule finds it."""
    monkeypatch.chdir(tmp_path)
    remote = tmp_path / "origin.git"
    remote.mkdir()
    _run_git(args=["init", "--bare", "--quiet", str(remote)], cwd=tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(args=["init", "--quiet", "--initial-branch=main"], cwd=repo)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)
    _write(path=repo / _WORKFLOW, text="name: ci\n")
    _write(path=repo / ".gitignore", text="/dev-tooling/\n")
    _commit_all(repo=repo, message="base")
    _run_git(args=["remote", "add", "origin", str(remote)], cwd=repo)
    _run_git(args=["push", "--quiet", "-u", "origin", "main"], cwd=repo)
    _run_git(args=["checkout", "--quiet", "-b", "feature/wip"], cwd=repo)
    _install_guard(repo=repo)
    _edit_workflow(repo=repo, commit=True)

    completed = _run_guard(repo=repo)

    assert completed.returncode == 1, completed.stderr
    assert str(_WORKFLOW) in completed.stderr
