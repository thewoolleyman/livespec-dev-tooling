"""Naming the GATED repository when the clone's origin is the in-cluster git daemon.

R4.S7 slice B (`livespec-dev-tooling-rwmo.2`), plan livespec
`k3s-on-gmktec-for-vps-usage` (epic `livespec-sab5gn`), design in that plan's
`research/003` sections E and H.

THE GAP THIS CLOSES. `credential-reading-targets.md` states it as the half of
the provisioning a token does not buy: both `gh api` checks name their
repository from the CLONE — `branch_protection_alignment` parses
`git remote get-url origin` against a github.com-only pattern, and
`master_ci_green` hands `gh` the `{owner}/{repo}` placeholders, which `gh`
expands from that same remote. A gate pod's origin is
`git://git-gates.gates.svc.cluster.local/<repo>.git` (section E), which is not
github.com and never will be, so with a perfectly good token in hand both
checks fail to identify the repository they are gating.

WHY THE FIX IS A DECLARED INPUT RATHER THAN A REWRITTEN ORIGIN. `origin` in a
gate pod is load-bearing for something else: the initContainer fetches the gate
ref AND its `.base` companion into `refs/remotes/origin/master`, which is the
name eight range-judging members of the aggregate resolve. Repointing it at
github.com would either break that fetch or demand a second remote the
github.com-only pattern still would not read. So the gate NAMES the repository
it is judging, in the same place and the same way it already declares that it
IS a gate — explicitly, by whoever runs it, never inferred.

WHAT EACH TEST HOLDS. The pure tests pin the reader, including the property
that makes the input safe to ship: outside a gate the variable is INERT, so it
cannot silently repoint a contributor's checks at another repository. The two
check-level tests drive `main()` against a real `git init` clone whose only
remote is the daemon URL, and assert the ADDRESS the check put on the wire.
Each is paired with the same clone and no declaration, where the check must
fail rather than pass — the negative control that keeps the positive one from
being a test of the fake `gh` instead of the resolution.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import branch_protection_alignment, master_ci_green
from livespec_dev_tooling.checks._gate_context import (
    GATE_CONTEXT_ENV,
    GATE_REPOSITORY_ENV,
    gate_repository,
)

__all__: list[str] = []


# The URL R4.S4 serves the tree from, verbatim from
# `ci-runner/k3s/phase2/gates/render-gate-job.sh`'s `--source-url` default. It
# is the whole precondition: a remote that is not github.com and carries no
# owner segment at all.
_DAEMON_ORIGIN = "git://git-gates.gates.svc.cluster.local/livespec-dev-tooling.git"
# The repository that clone is a copy of — knowable only from the declaration,
# never from the remote above.
_GATED_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
# The two addresses each check must reach once it has resolved the repository.
_PROTECTION_PATH = f"repos/{_GATED_REPOSITORY}/branches/master/protection/required_status_checks"
_CHECK_RUNS_PATH = f"repos/{_GATED_REPOSITORY}/commits/master/check-runs?check_name=ci-green"
# What `gh` puts on the wire when nothing has told it otherwise. Asserted
# ABSENT from the gate run's invocations: `gh` expands these from the clone's
# own remote, which in a gate pod cannot answer.
_GH_PLACEHOLDERS = "repos/{owner}/{repo}"
# Scrubbed so the host's git config cannot reach the fixture clone — a global
# `url.<base>.insteadOf` rewriting `git://` would otherwise change the very
# remote this suite exists to reproduce.
_SCRUBBED_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
}


def _daemon_origin_clone(*, root: Path) -> None:
    """Create a real clone at `root` whose only remote is the git daemon.

    A REAL repository rather than a stubbed `git`: the resolution under test is
    exactly "what does this clone say it is", so faking git's answer would move
    the precondition into the fixture and prove nothing about a gate pod.
    """
    _ = subprocess.run(["git", "init", "--quiet", str(root)], check=True, env=_SCRUBBED_GIT_ENV)
    _ = subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", _DAEMON_ORIGIN],
        check=True,
        env=_SCRUBBED_GIT_ENV,
    )


def _write_ci_yml(*, root: Path) -> None:
    """A ci.yml aligned with the required list the fake `gh` reports.

    One matrix leg plus the `ci-green` top-level aggregate gate, which is the
    single-gate shape the required list below names — so a run that reaches the
    alignment gate at all passes it, and the exit code stays a statement about
    resolution rather than about drift.
    """
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    ci_yml = (
        "name: CI\n"
        "on: push\n"
        "jobs:\n"
        "  check:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          - check-foo\n"
        "    runs-on: ubuntu-latest\n"
        "  ci-green:\n"
        "    needs: [check]\n"
        "    runs-on: ubuntu-latest\n"
    )
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")


def _invocations(*, root: Path) -> str:
    """Every `gh api` argv the run issued, one per line."""
    log = root / "bin" / "gh.argv"
    return log.read_text(encoding="utf-8") if log.is_file() else ""


def _install_fake_gh(*, root: Path) -> str:
    """Install a fake `gh` under `root/bin` and return a PATH that finds it first.

    It answers ONLY the four addresses that name `_GATED_REPOSITORY` and refuses
    everything else the way the real API does (a JSON body on stdout, a rendered
    line on stderr, non-zero exit). That refusal is what makes the negative
    controls meaningful: a check that resolved the wrong repository does not
    quietly read someone else's state, it comes back empty-handed.

    `gh auth token` exits 0 — a credential IS present, which is slice C's half
    of the provisioning — and is deliberately not logged: it is a local probe,
    not an address the check chose.
    """
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    answers = {
        f"repos/{_GATED_REPOSITORY}": '{"default_branch": "master"}',
        _PROTECTION_PATH: '{"strict": false, "contexts": ["ci-green"]}',
        f"repos/{_GATED_REPOSITORY}/branches/master/protection/enforce_admins": (
            '{"enabled": true}'
        ),
        _CHECK_RUNS_PATH: (
            '{"total_count": 1, "check_runs": '
            '[{"name": "ci-green", "status": "completed", "conclusion": "success"}]}'
        ),
    }
    # Literal `[ "$2" = ... ]` comparisons rather than a `case`: one address
    # carries a `?` query string, which a `case` pattern would read as a
    # single-character wildcard and match far too much.
    dispatch = "".join(
        f"if [ \"$2\" = \"{path}\" ]; then\n  printf '%s\\n' '{payload}'\n  exit 0\nfi\n"
        for path, payload in answers.items()
    )
    script = (
        "#!/bin/sh\n"
        'if [ "$1" = "auth" ]; then\n  exit 0\nfi\n'
        f"printf '%s\\n' \"$*\" >> '{bin_dir}/gh.argv'\n"
        f"{dispatch}"
        "printf '%s\\n' '{\"message\": \"Not Found\"}'\n"
        "echo 'gh: Not Found (HTTP 404)' >&2\n"
        "exit 1\n"
    )
    _ = gh_path.write_text(script, encoding="utf-8")
    gh_path.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def _stage_gate_pod(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declare_repository: bool,
) -> None:
    """Put the process in a gate pod's position: daemon origin, token, gate signal.

    `declare_repository` is the ONE variable between the positive case and its
    control, so a difference in outcome can only be attributed to the
    declaration.
    """
    _daemon_origin_clone(root=tmp_path)
    _write_ci_yml(root=tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", _install_fake_gh(root=tmp_path))
    monkeypatch.setenv(GATE_CONTEXT_ENV, "1")
    if declare_repository:
        monkeypatch.setenv(GATE_REPOSITORY_ENV, _GATED_REPOSITORY)
    else:
        monkeypatch.delenv(GATE_REPOSITORY_ENV, raising=False)


def test_an_undeclared_repository_reads_as_absent(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """A gate that named no repository has not named one."""
    monkeypatch.delenv(GATE_REPOSITORY_ENV, raising=False)
    assert gate_repository(env={GATE_CONTEXT_ENV: "1"}) is None


def test_a_declared_repository_is_returned_inside_a_gate() -> None:
    assert (
        gate_repository(env={GATE_CONTEXT_ENV: "1", GATE_REPOSITORY_ENV: _GATED_REPOSITORY})
        == _GATED_REPOSITORY
    )


def test_the_declaration_is_inert_outside_a_gate() -> None:
    """The property that makes this input safe to ship to every consumer.

    Read unconditionally, an environment variable naming a repository would let
    anything in a contributor's shell silently point `check-master-ci-green` at
    a repository they are not on — and it would report that repository's master
    as this one's. Honouring it only where the gate context is declared keeps
    the blast radius inside the pod that set both.
    """
    assert gate_repository(env={GATE_REPOSITORY_ENV: _GATED_REPOSITORY}) is None


@pytest.mark.parametrize(
    "declared",
    ["", "   ", "livespec-dev-tooling", "owner/repo/extra", "https://github.com/owner/repo"],
)
def test_a_value_that_is_not_an_owner_repo_pair_is_refused(*, declared: str) -> None:
    """Shape-checked before use, because the value is pasted into an API path.

    Every rejected form here is one a hand-set variable plausibly carries — a
    bare repository name, a URL, a path with an extra segment — and each would
    otherwise become a `gh api repos/...` request for something that is not a
    repository. Refusing leaves the check with no repository, which inside a
    gate is a failure; accepting would make it a request nobody can read.
    """
    assert gate_repository(env={GATE_CONTEXT_ENV: "1", GATE_REPOSITORY_ENV: declared}) is None


def test_branch_protection_reads_the_declared_repository_over_a_daemon_origin(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The gated repo's protection IS read, from a clone that cannot name it.

    The address is the assertion: `repos/<owner>/<repo>/branches/master/
    protection/required_status_checks` proves the check resolved a github.com
    repository from a `git://` remote, and reaching exit 0 proves it went on to
    perform the branch-protection read rather than skip-passing short of it.
    """
    _stage_gate_pod(tmp_path=tmp_path, monkeypatch=monkeypatch, declare_repository=True)
    rc = branch_protection_alignment.main()
    captured = capsys.readouterr()
    assert rc == 0, f"expected the protection read to succeed; stderr={captured.err!r}"
    assert _PROTECTION_PATH in _invocations(root=tmp_path), (
        f"the branch-protection read never addressed the gated repository; "
        f"gh was invoked as: {_invocations(root=tmp_path)!r}"
    )


def test_branch_protection_fails_in_a_gate_that_declared_no_repository(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The control: without the declaration the daemon origin is still unreadable.

    Same clone, same token, same gate — so the previous test's pass is
    attributable to the declaration and to nothing else. Exit 1 is R4.S6's
    disposition holding: a gate that could not read branch protection does not
    report a pass.
    """
    _stage_gate_pod(tmp_path=tmp_path, monkeypatch=monkeypatch, declare_repository=False)
    rc = branch_protection_alignment.main()
    captured = capsys.readouterr()
    assert rc == 1, f"expected a gate with no resolvable repository to fail; rc={rc}"
    assert "did not match github.com pattern" in captured.err


def test_master_ci_green_reads_the_declared_repository_over_a_daemon_origin(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The head-commit `ci-green` signal is read at the gated repository's address.

    The placeholder form is asserted ABSENT as well as the resolved form
    present: `{owner}/{repo}` is not an error `gh` reports back, it is an
    expansion that silently resolves to whatever the clone's remote says — so a
    regression here would look like a working check pointed at nothing.
    """
    _stage_gate_pod(tmp_path=tmp_path, monkeypatch=monkeypatch, declare_repository=True)
    rc = master_ci_green.main()
    captured = capsys.readouterr()
    assert rc == 0, f"expected master CI to read green; stderr={captured.err!r}"
    invocations = _invocations(root=tmp_path)
    assert _CHECK_RUNS_PATH in invocations, (
        f"the master-CI read never addressed the gated repository; "
        f"gh was invoked as: {invocations!r}"
    )
    assert _GH_PLACEHOLDERS not in invocations, (
        f"the gate still asked `gh` to expand the repository from the clone; "
        f"gh was invoked as: {invocations!r}"
    )


def test_master_ci_green_fails_in_a_gate_that_declared_no_repository(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The control: the placeholder form reaches an API that cannot answer it.

    A credentialed call that failed is `unprovable`, not a skip — the gate ran,
    it did not come back with a green master, and it says so.
    """
    _stage_gate_pod(tmp_path=tmp_path, monkeypatch=monkeypatch, declare_repository=False)
    rc = master_ci_green.main()
    captured = capsys.readouterr()
    assert rc == 1, f"expected a gate with no resolvable repository to fail; rc={rc}"
    assert _GH_PLACEHOLDERS in _invocations(root=tmp_path)
    assert "cannot prove master CI is green" in captured.err
