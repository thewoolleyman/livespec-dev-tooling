"""Delegated pre-commit aggregate decisions."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "pre_commit_delegate.py"

_REPO_ROOT = Path(__file__).parents[2]

__all__: list[str] = []


def _module() -> object:
    """Import the seam only after the Red assertion has run."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling.pre_commit_delegate")


def test_an_absent_pre_commit_opt_in_runs_locally(*, tmp_path: Path) -> None:
    """A repository must explicitly opt in before its pre-commit gate delegates."""
    module = _module()

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.reason == "delegated_pre_commit is not enabled"


def test_an_unreadable_gates_kubeconfig_runs_the_pre_commit_gate_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An opted-in repository without the host credential retains its local gate."""
    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: False)

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.reason == "gates kubeconfig is not readable"


def test_a_credentialed_pre_commit_delegates_the_staged_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Job preserves its declared bootstrap before replacing its aggregate."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n"
        "delegated_pre_commit = true\n"
        "gate_check_suite = [\n"
        '    "install-worktree-pack",\n'
        '    "install-commit-refuse-hooks",\n'
        '    "warm-typecheck",\n'
        '    "hook_gate=1 check",\n'
        "]\n",
        encoding="utf-8",
    )
    request = GateRunRequest(
        repo_root=tmp_path,
        mirror_url="mirror",
        manifest="manifest",
        gate_ref="refs/gates/tree",
    )
    captured: dict[str, object] = {}

    def build(**kwargs: object) -> object:
        captured.update(kwargs)
        return Success(request)

    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "gate_remote_request", build)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_PASSED,
            detail="the Job passed",
            token_written=True,
            job_name="gate-pre-commit-1",
            tree_hash="a" * 40,
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert captured["tree_hash"] == "a" * 40
    assert captured["check_suite"] == (
        "install-worktree-pack",
        "install-commit-refuse-hooks",
        "warm-typecheck",
        "check-pre-commit-gated-tree",
    )
    assert verdict.local is False
    assert verdict.job_name == "gate-pre-commit-1"
    assert verdict.tree_hash == "a" * 40
    assert verdict.exit_status == 0


def test_this_repository_enables_delegated_pre_commit_after_the_bootstrap_fix() -> None:
    """The released dev-tooling configuration opts into the repaired Job path."""
    from livespec_dev_tooling.config import load_delegated_pre_commit

    assert load_delegated_pre_commit(repo_root=_REPO_ROOT) is True


def test_an_unreadable_declared_suite_gates_the_pre_commit_aggregate_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A suite declaration the remote client cannot read retains the local gate."""
    from returns.result import Failure

    from livespec_dev_tooling.gate_remote_invocation import GateStepFailed

    module = _module()
    assert hasattr(module, "_pre_commit_check_suite")
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(
        module,
        "declared_gate_check_suite",
        lambda **_kwargs: Failure(
            GateStepFailed(step="read-gate-check-suite", argv=(), returncode=1, detail="bad suite")
        ),
        raising=False,
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.tree_hash == "a" * 40
    assert "gate check suite could not be read" in verdict.reason


@pytest.mark.parametrize(
    "remote",
    [
        {"state": "NO_VERDICT", "tree_hash": None},
        {"state": "PASSED", "tree_hash": "b" * 40},
    ],
)
def test_an_absent_or_wrong_tree_cluster_outcome_gates_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: dict[str, str | None]
) -> None:
    """Only a verdict naming the staged tree may keep the local aggregate out."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=tmp_path,
                mirror_url="mirror",
                manifest="manifest",
                gate_ref="refs/gates/tree",
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=remote["state"],
            detail="the cluster could not provide the staged-tree verdict",
            token_written=False,
            tree_hash=remote["tree_hash"],
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.exit_status is None
    assert verdict.tree_hash == "a" * 40


@pytest.mark.parametrize(
    ("returncode", "expected_status"),
    [(0, 0), (1, 1), (None, 1)],
)
def test_a_green_pre_commit_job_is_joined_with_the_host_authority_members(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    returncode: int | None,
    expected_status: int,
) -> None:
    """A green Job never accepts a commit the committing host's authority members refuse."""
    from returns.result import Success

    from livespec_dev_tooling._gate_host_authority import HostAuthorityRun
    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    def authority(**kwargs: object) -> tuple[HostAuthorityRun, ...]:
        seen.update(kwargs)
        return (
            HostAuthorityRun(
                member="check-no-workflow-edits",
                tree_hash="a" * 40,
                returncode=returncode,
                detail="unauthorized workflow edit",
            ),
        )

    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=tmp_path,
                mirror_url="mirror",
                manifest="manifest",
                gate_ref="refs/gates/tree",
            )
        ),
    )
    monkeypatch.setattr(module, "run_host_authority_members", authority)
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_PASSED,
            detail="the Job passed",
            token_written=True,
            job_name="gate-pre-commit-1",
            tree_hash="a" * 40,
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert seen["repo_root"] == tmp_path
    assert seen["tree_hash"] == "a" * 40
    assert verdict.local is False
    assert verdict.exit_status == expected_status
    assert verdict.job_name == "gate-pre-commit-1"
    if expected_status:
        assert "check-no-workflow-edits" in verdict.reason


def _git(*, cwd: Path, args: list[str]) -> str:
    """Run one git command in a throwaway repository and return its stdout."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") or key == "GIT_CONFIG_NOSYSTEM"
    }
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_the_gated_tree_recipe_restores_the_staged_index_before_the_aggregate(
    *, tmp_path: Path
) -> None:
    """The Job's clean checkout must present the aggregate the hook's staged-tree state.

    The gate Job checks out the staged-tree commit, where `git diff --cached` is empty, so
    the hook's empty-staged short-circuit would pass without running a member. The gated-tree
    recipe rewinds HEAD to the commit's parent while keeping the index and working tree, so
    the unchanged aggregate sees the same staged files and the same `HEAD` the hook saw.
    """
    scripts = tmp_path / "scripts" / "just"
    scripts.mkdir(parents=True)
    recipe = _REPO_ROOT / "scripts" / "just" / "check-pre-commit-gated-tree.sh"
    assert recipe.is_file()
    _ = shutil.copy(recipe, scripts / recipe.name)
    seen = tmp_path / "seen.txt"
    stub = scripts / "check-pre-commit.sh"
    _ = stub.write_text(
        "#!/usr/bin/env bash\n"
        f'{{ git rev-parse HEAD; git diff --cached --name-only; }} > "{seen}"\n'
        "exit 7\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    _git(cwd=tmp_path, args=["init", "-q", "-b", "main"])
    _ = (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "base.txt", "scripts"])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "base"])
    parent = _git(cwd=tmp_path, args=["rev-parse", "HEAD"])
    _ = (tmp_path / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "staged.txt"])
    tree = _git(cwd=tmp_path, args=["write-tree"])
    commit = _git(cwd=tmp_path, args=["commit-tree", tree, "-p", parent, "-m", "staged"])
    _git(cwd=tmp_path, args=["reset", "-q", "--hard", commit])

    ran = subprocess.run(
        ["bash", str(scripts / recipe.name)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 7
    assert seen.read_text(encoding="utf-8").split() == [parent, "staged.txt"]
    assert _git(cwd=tmp_path, args=["write-tree"]) == tree


def _dirty_the_tree(*, tmp_path: Path, dirty: str) -> None:
    """Leave the tree dirty in the one way `dirty` names, after staging base.py."""
    if dirty == "unstaged":
        _ = (tmp_path / "base.py").write_text("base = 3\n", encoding="utf-8")
    elif dirty == "untracked":
        _ = (tmp_path / "conftest.py").write_text("x = 1\n", encoding="utf-8")
    elif dirty == "ignored":
        _ = (tmp_path / "ignored.txt").write_text("x\n", encoding="utf-8")


def _run_pre_commit_with_stub_aggregate(*, tmp_path: Path, dirty: str) -> list[str]:
    """Run the shipped pre-commit recipe with a passing full-aggregate stub."""
    scripts = tmp_path / "scripts" / "just"
    scripts.mkdir(parents=True)
    _ = shutil.copy(_REPO_ROOT / "scripts" / "just" / "check-pre-commit.sh", scripts)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    writes = tmp_path / "writes.txt"
    uv = bin_dir / "uv"
    _ = uv.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        "  *pre_commit_delegate*) exit 75 ;;\n"
        f'  *write-pre-commit*) echo "$*" >> "{writes}" ;;\n'
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    just = bin_dir / "just"
    moves_index = "echo moved > moved.txt\ngit add moved.txt\n" if dirty == "index-moves" else ""
    _ = just.write_text(
        f"#!/usr/bin/env bash\n{moves_index}echo aggregate-ok\nexit 0\n", encoding="utf-8"
    )
    uv.chmod(0o755)
    just.chmod(0o755)
    _git(cwd=tmp_path, args=["init", "-q", "-b", "main"])
    _ = (tmp_path / ".gitignore").write_text("bin/\nwrites.txt\nignored.txt\n", encoding="utf-8")
    _ = (tmp_path / "base.py").write_text("base = 1\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", ".gitignore", "base.py", "scripts"])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "base"])
    _ = (tmp_path / "base.py").write_text("base = 2\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "base.py"])
    _dirty_the_tree(tmp_path=tmp_path, dirty=dirty)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") or key == "GIT_CONFIG_NOSYSTEM"
    }
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    ran = subprocess.run(
        ["bash", str(scripts / "check-pre-commit.sh")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ran.returncode == 0, ran.stderr
    return writes.read_text(encoding="utf-8").splitlines() if writes.exists() else []


def test_only_a_clean_full_pre_commit_aggregate_records_reusable_evidence(
    *, tmp_path: Path
) -> None:
    """Unstaged, untracked, or mid-run index changes make the aggregate a different-tree verdict."""
    cases = (("none", 1), ("ignored", 1), ("unstaged", 0), ("untracked", 0), ("index-moves", 0))
    for dirty, expected_writes in cases:
        sub = tmp_path / dirty
        sub.mkdir()
        assert (
            len(_run_pre_commit_with_stub_aggregate(tmp_path=sub, dirty=dirty)) == expected_writes
        )


def _run_main_with_delegated_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **verdict_fields: object
) -> tuple[int, dict[str, object]]:
    """Run the delegate's CLI with a stubbed verdict; return its status and token."""
    module = _module()
    _git(cwd=tmp_path, args=["init", "-q", "-b", "main"])
    scrubbed = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["pre_commit_delegate", "run"])
    monkeypatch.setattr(
        module, "run_pre_commit", lambda **_kwargs: module.PreCommitVerdict(**verdict_fields)
    )
    with mock.patch.dict(os.environ, scrubbed, clear=True):
        status = module.main()
    token_path = tmp_path / ".git" / "livespec-green-token.json"
    token = json.loads(token_path.read_text(encoding="utf-8")) if token_path.exists() else {}
    return status, token


def test_a_passing_delegated_aggregate_records_reusable_same_tree_evidence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A green gate Job verdict is the full aggregate, so commit-msg may reuse it."""
    status, token = _run_main_with_delegated_verdict(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        local=False,
        reason="the Job passed",
        job_name="gate-pre-commit-1",
        tree_hash="a" * 40,
        exit_status=0,
        output_checksum="sha256:job-output",
        full_aggregate=True,
    )

    assert status == 0
    assert "pre_commit_aggregate" in token
    evidence = token["pre_commit_aggregate"]
    assert token["tree_hash"] == "a" * 40
    assert evidence["tree_hash"] == "a" * 40
    assert "gate-pre-commit-1" in evidence["run_id"]
    assert evidence["output_checksum"] == "sha256:job-output"


def test_a_failed_or_unattributable_delegated_aggregate_records_no_evidence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a passed verdict naming its tree, Job, and output may stand in for the suite."""
    cases: list[dict[str, object]] = [
        {
            "exit_status": 1,
            "output_checksum": "sha256:job-output",
            "job_name": "gate-1",
            "full_aggregate": True,
        },
        {"exit_status": 0, "output_checksum": None, "job_name": "gate-1", "full_aggregate": True},
        {
            "exit_status": 0,
            "output_checksum": "sha256:job-output",
            "job_name": None,
            "full_aggregate": True,
        },
        {
            "exit_status": 0,
            "output_checksum": "sha256:job-output",
            "job_name": "gate-1",
            "tree_hash": None,
            "full_aggregate": True,
        },
    ]
    for index, case in enumerate(cases):
        sub = tmp_path / str(index)
        sub.mkdir()
        fields: dict[str, object] = {"local": False, "reason": "r", "tree_hash": "a" * 40, **case}
        _, token = _run_main_with_delegated_verdict(tmp_path=sub, monkeypatch=monkeypatch, **fields)
        assert token == {}, case


def _stage_repo(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> str:
    """Build a repo with one base commit, stage `files`, and return the staged tree."""
    monkeypatch.setenv("GIT_LIVESPEC_STRIP_PROBE", "1")
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        monkeypatch.delenv(name)
    _git(cwd=tmp_path, args=["init", "-q", "-b", "main"])
    _ = (tmp_path / "keep.py").write_text("KEEP = 1\n", encoding="utf-8")
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n", encoding="utf-8"
    )
    _git(cwd=tmp_path, args=["add", "-A"])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "base"])
    for name, body in files.items():
        if name == "RENAME-keep.py":
            _git(cwd=tmp_path, args=["mv", "keep.py", "renamed.py"])
            continue
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(body, encoding="utf-8")
        _git(cwd=tmp_path, args=["add", name])
    return _git(cwd=tmp_path, args=["write-tree"])


@pytest.mark.parametrize(
    ("files", "ran_full_aggregate"),
    [
        ({"docs/readme.md": "x\n"}, False),
        ({"tests/test_new.py": "x = 1\n"}, False),
        ({"RENAME-keep.py": ""}, False),
        ({"pkg/impl.py": "x = 1\n"}, True),
        ({"tests/test_new.py": "x = 1\n", "pkg/impl.py": "x = 1\n"}, False),
        ({"tests/test_new.py": "x = 1\n", "ansible/files/foo.py": "x = 1\n"}, False),
        ({"tests/test_new.py": "x = 1\n", "livespec_dev_tooling/impl.py": "x = 1\n"}, True),
        ({"tests/test_a.py": "x = 1\n", "tests/test_b.py": "x = 1\n"}, True),
    ],
)
def test_a_delegated_pass_claims_the_full_aggregate_only_when_the_staged_tree_selects_it(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    files: dict[str, str],
    ran_full_aggregate: bool,
) -> None:
    """A Job that passed on the doc-only or Red-leg subset is not a full-aggregate pass."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = _module()
    tree = _stage_repo(tmp_path=tmp_path, monkeypatch=monkeypatch, files=files)
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "run_host_authority_members", lambda **_kwargs: ())
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=tmp_path,
                mirror_url="mirror",
                manifest="manifest",
                gate_ref="refs/gates/tree",
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_PASSED,
            detail="the Job passed",
            token_written=True,
            job_name="gate-pre-commit-1",
            tree_hash=tree,
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.exit_status == 0
    assert getattr(verdict, "full_aggregate", None) is ran_full_aggregate


def test_a_delegated_pass_on_a_non_full_subset_records_no_evidence_and_says_so(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A doc-only pass must leave no token the pre-push gate could memoize the suite on."""
    status, token = _run_main_with_delegated_verdict(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        local=False,
        reason="the Job passed",
        job_name="gate-pre-commit-1",
        tree_hash="a" * 40,
        exit_status=0,
        output_checksum="sha256:job-output",
        full_aggregate=False,
    )

    assert status == 0
    assert token == {}
    output = capsys.readouterr().err
    assert "no pre-commit aggregate evidence recorded" in output
    assert "a" * 40 in output
    assert "gate-pre-commit-1" in output
