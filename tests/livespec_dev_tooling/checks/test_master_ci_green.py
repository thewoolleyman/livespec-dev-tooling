"""Outside-in test for `dev-tooling/checks/master_ci_green.py`.

Guard Layer 1 mechanical check that prevents the silent-red-master
pattern: master CI failed weeks ago, every PR merged onto red master
inherited the brokenness. The check ensures master CI is green at
every commit.

Two axes are exercised separately.

SIGNAL. The check reads the `ci-green` CHECK RUN on master's head
commit — the signal branch protection evaluates — and never the latest
master WORKFLOW RUN's conclusion, which is a different signal that can
disagree with it in both directions. `test_reads_head_commit_ci_green_
check_run_not_the_workflow_run` pins that disagreement: the fake `gh`
answers `run list` with a red run and the check-runs endpoint with a
green `ci-green`, and the check must follow branch protection.

`gh` FAILURE STATES. Five are tested separately, because they do not
deserve the same answer. A host with no `gh` binary, a host whose `gh`
holds no credential, a host whose credential is rejected with HTTP 401,
and a repo whose `master` ref does not resolve were never able to check
at all and skip gracefully so local pre-commit is not blocked. A host
whose credentialed API call fails for any other reason attempted the
check and got no answer — it has not proven master is green, so it
fails loudly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "master_ci_green.py"
# The endpoint the check must query: master's HEAD COMMIT, filtered to the
# `ci-green` check run branch protection requires. `{owner}`/`{repo}` are
# `gh api` placeholders, expanded by `gh` from the current repo's remote.
_EXPECTED_ENDPOINT = "repos/{owner}/{repo}/commits/master/check-runs?check_name=ci-green"


def _run_check(
    *,
    cwd: Path,
    env_path: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the check script with cwd set to a path.

    Preserves the parent env (incl. COVERAGE_PROCESS_START) so pytest-cov's
    subprocess auto-init works; overrides only PATH when env_path is given,
    plus any explicit `env_extra` entries (e.g. pinning an env var a test's
    expectation depends on, so it cannot flip with the invoking shell's env).
    """
    env = {**os.environ, **(env_extra or {})}
    if env_path is not None:
        env["PATH"] = env_path
    return subprocess.run(
        [sys.executable, str(_CHECK)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_gh_unavailable_skips_gracefully(*, tmp_path: Path) -> None:
    """No `gh` on PATH → exit 0 with a warning (local-dev tolerance)."""
    result = _run_check(cwd=tmp_path, env_path="")
    assert result.returncode == 0, (
        f"expected exit 0 when gh unavailable; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "gh CLI not on PATH" in result.stderr


def test_real_repo_passes(*, tmp_path: Path) -> None:  # noqa: ARG001
    """Run the check against the real repo cwd; expect exit 0.

    Exercises the real-`gh` path end-to-end against a green master (a red
    master legitimately fails this test — that is the gate working; the
    remedy is to revert whatever reddened master, never to soften this
    check). With `gh` unauthenticated the check still exits 0 (graceful
    skip).
    """
    result = _run_check(cwd=_REPO_ROOT)
    assert result.returncode == 0, (
        f"expected exit 0 against real repo; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def _invocation_log(*, tmp_path: Path) -> Path:
    """Path the fake `gh` appends one line per invocation to."""
    return tmp_path / "gh-invocations.log"


def _install_fake_gh(
    *,
    tmp_path: Path,
    stdout: str = '{"total_count": 0, "check_runs": []}',
    stderr: str = "",
    returncode: int = 0,
    auth_returncode: int = 0,
) -> str:
    """Install a fake `gh` shell stub at tmp_path/bin/gh, return PATH including it.

    The stub dispatches on the sub-command so the check's distinct `gh`
    invocations can be driven independently, and appends every invocation's
    argv to `_invocation_log(...)` so a test can assert WHICH signal was read:

    - `gh auth token` — the local credential probe. Exits `auth_returncode`
      (0 = a credential is stored, 1 = none), printing nothing, mirroring the
      real `gh` closely enough for the check while never emitting a token.
      Deliberately NOT logged: it is a local probe, not a signal read.
    - `gh run list ...` — the WORKFLOW-RUN signal the check must no longer
      read. It always answers RED, so any test that passes proves the check
      did not consult it.
    - anything else (i.e. `gh api ...`) — prints `stdout` to stdout,
      `stderr` to stderr, and exits `returncode`.

    `auth_returncode` defaults to 0 because the credential probe only runs on
    the API-failure path, so a credentialed default leaves every happy-path
    test's behavior unchanged.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    log_path = _invocation_log(tmp_path=tmp_path)
    script = (
        "#!/bin/sh\n"
        'if [ "$1" = "auth" ] && [ "$2" = "token" ]; then\n'
        f"  exit {auth_returncode}\n"
        "fi\n"
        f"echo \"$@\" >> '{log_path}'\n"
        'if [ "$1" = "run" ]; then\n'
        '  echo \'[{"status": "completed", "conclusion": "failure"}]\'\n'
        "  exit 0\n"
        "fi\n"
        f"cat <<'STUB_EOF'\n{stdout}\nSTUB_EOF\n"
        f"cat >&2 <<'STUB_EOF'\n{stderr}\nSTUB_EOF\n"
        f"exit {returncode}\n"
    )
    _ = gh_path.write_text(script, encoding="utf-8")
    gh_path.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def _check_runs_payload(*, status: str, conclusion: str) -> str:
    """A one-entry `check-runs` response body for the `ci-green` check run."""
    return (
        '{"total_count": 1, "check_runs": [{"name": "ci-green", '
        f'"status": "{status}", "conclusion": {conclusion}}}]}}'
    )


def test_reads_head_commit_ci_green_check_run_not_the_workflow_run(*, tmp_path: Path) -> None:
    """Master's newest workflow run is RED while head-commit `ci-green` is green → exit 0.

    Regression pin for work-item livespec-dev-tooling-aa7 (absorbing gam8 and
    8o8e.22): the check used to read `gh run list --branch master --limit 1`,
    a DIFFERENT signal from the one branch protection evaluates. A workflow
    run concludes `failure` when a NON-gating job fails (`export-telemetry` is
    deliberately absent from `ci-green`'s `needs:`) and `cancelled` when it is
    superseded, while the head commit's required `ci-green` context stands at
    `success`. Reading the run conclusion therefore rejected work while master
    was genuinely mergeable. The gate must read what the merge gate reads.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_check_runs_payload(status="completed", conclusion='"success"'),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 when head-commit ci-green is success despite a red "
        f"workflow run; got {result.returncode}, stderr={result.stderr!r}"
    )
    invocations = _invocation_log(tmp_path=tmp_path).read_text(encoding="utf-8")
    assert _EXPECTED_ENDPOINT in invocations, (
        f"expected the head-commit ci-green check-runs endpoint to be queried; "
        f"gh was invoked as: {invocations!r}"
    )
    assert "run list" not in invocations, (
        f"the workflow-run signal must never be consulted; " f"gh was invoked as: {invocations!r}"
    )


def test_success_conclusion_passes(*, tmp_path: Path) -> None:
    """Head-commit ci-green is success → exit 0."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_check_runs_payload(status="completed", conclusion='"success"'),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0


def test_failure_conclusion_fails(*, tmp_path: Path) -> None:
    """Head-commit ci-green is failure → exit 1 with error diagnostic."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_check_runs_payload(status="completed", conclusion='"failure"'),
    )
    result = _run_check(
        cwd=tmp_path,
        env_path=fake_path,
        env_extra={"LIVESPEC_MASTER_CI_GREEN": ""},
    )
    assert result.returncode == 1
    assert "master CI is red" in result.stderr


def test_red_conclusion_fails_regardless_of_lever_env(*, tmp_path: Path) -> None:
    """A red master fails even with `LIVESPEC_MASTER_CI_GREEN=warn` in the env.

    This gate deliberately has NO escape lever (wontfix li-4x3a45, upheld and
    broadened by maintainer directive 2026-07-04 after a warn lever briefly
    landed and was removed the same day): an env var that demotes a red
    master to a warning lets agents push onto a broken master, which is the
    exact failure the check exists to prevent. The remedy for a gate
    deadlock is a server-side revert PR of the breaking change and a
    re-land in the right order — never a bypass. This test pins the env var
    to having NO effect so the lever cannot be quietly reintroduced.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_check_runs_payload(status="completed", conclusion='"failure"'),
    )
    result = _run_check(
        cwd=tmp_path,
        env_path=fake_path,
        env_extra={"LIVESPEC_MASTER_CI_GREEN": "warn"},
    )
    assert result.returncode == 1
    assert "master CI is red" in result.stderr


def test_pending_status_passes(*, tmp_path: Path) -> None:
    """Head-commit ci-green still in_progress → exit 0 with info log."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_check_runs_payload(status="in_progress", conclusion="null"),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "still pending" in result.stderr


def test_unrecognized_conclusion_passes(*, tmp_path: Path) -> None:
    """Unrecognized conclusion → exit 0 with warning (non-blocking)."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_check_runs_payload(status="completed", conclusion='"neutral"'),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "unrecognized conclusion" in result.stderr


def test_empty_check_runs_list_skips(*, tmp_path: Path) -> None:
    """No ci-green check run on master's head commit → exit 0 with warning."""
    fake_path = _install_fake_gh(tmp_path=tmp_path)
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "no ci-green check run on master" in result.stderr


def test_missing_master_ref_skips_gracefully(*, tmp_path: Path) -> None:
    """The `master` ref does not resolve on the remote → exit 0 with warning.

    A governed repo whose default branch is `main` has no `master` commit to
    read, and GitHub answers the commits endpoint with the canonical
    "No commit found for SHA" body. That host could never learn master's CI
    state, which is the environmental category, NOT the outage category — so
    it skips rather than failing loudly, exactly as the empty run list did
    before the signal changed.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"message": "No commit found for SHA: master", "status": "422"}',
        stderr="gh: No commit found for SHA: master (HTTP 422)",
        returncode=1,
        auth_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 when the master ref does not resolve; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "master ref does not resolve" in result.stderr


def test_gh_api_failure_without_credential_skips_gracefully(*, tmp_path: Path) -> None:
    """gh present but holding NO credential, API call fails → exit 0 with warning.

    This is the local-developer tolerance the fail-soft was built for: someone
    who never ran `gh auth login` cannot check master's CI state, and must not
    be blocked from running pre-commit. The hint points at authentication,
    which is the actual remedy here.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        returncode=1,
        auth_returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 when gh holds no credential; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "gh CLI has no stored credential" in result.stderr
    assert "gh auth login" in result.stderr


def test_credentialed_http_401_skips_as_invalid_credential(*, tmp_path: Path) -> None:
    """gh credential present but rejected with HTTP 401 → exit 0 with warning.

    `gh auth token` proves only local credential presence, not validity. An
    expired token arms the gate but still leaves this host unable to learn
    master's CI state, matching the no-credential environmental category.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        stderr="HTTP 401: Bad credentials",
        returncode=1,
        auth_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0, (
        f"expected exit 0 for rejected gh credential; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "gh credential was rejected" in result.stderr


def test_credentialed_http_503_still_fails_loudly(*, tmp_path: Path) -> None:
    """gh credential present but API returns HTTP 503 → exit 1, never a pass."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        stderr="HTTP 503: Service Unavailable",
        returncode=1,
        auth_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 1, (
        f"expected exit 1 when GitHub returns HTTP 503; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "cannot prove master CI is green" in result.stderr


def test_credentialed_rate_limit_fails_loudly(*, tmp_path: Path) -> None:
    """gh credential present but the API rate-limits the call → exit 1.

    A 403 rate-limit is the same category as the outage: the gate was armed,
    it ran, and it did not come back with a green master. Treating it as a
    skip would reopen the hole on exactly the busy host most likely to hit it.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        stderr="HTTP 403: API rate limit exceeded",
        returncode=1,
        auth_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 1, (
        f"expected exit 1 when the GitHub API rate-limits a credentialed call; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "cannot prove master CI is green" in result.stderr


def test_gh_api_failure_with_credential_fails_loudly(*, tmp_path: Path) -> None:
    """gh IS credentialed and the API call fails → exit 1, never a silent pass.

    Regression pin for the 2026-07-19 GitHub outage (work-item
    livespec-dev-tooling-aa7): an authenticated `gh` still returns HTTP 503
    when GitHub is down, and the old catch-all fail-soft exited 0 while master
    was genuinely red — the exact silent-red-master hole this gate exists to
    close. A caller that COULD have checked but got no answer has not proven
    master is green, so it does not pass.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        returncode=1,
        auth_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 1, (
        f"expected exit 1 when a credentialed gh cannot reach the API; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "cannot prove master CI is green" in result.stderr


def test_credentialed_api_failure_hint_is_not_the_auth_hint(*, tmp_path: Path) -> None:
    """The API-error hint must not misdiagnose an outage as an auth problem.

    The pre-fix code emitted `check gh auth status` for every failure branch
    including an HTTP 503, sending the reader somewhere useless. The two
    branches now carry distinct, separately-actionable hints; this pins that
    the credentialed branch does NOT reach for the authentication remedy.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        returncode=1,
        auth_returncode=0,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert "gh auth login" not in result.stderr
    assert "gh auth status" not in result.stderr
    assert "retry once the GitHub API is reachable" in result.stderr


def test_credentialed_api_failure_fails_regardless_of_lever_env(*, tmp_path: Path) -> None:
    """An unprovable master fails even with `LIVESPEC_MASTER_CI_GREEN=warn` set.

    Same standing directive as the red-conclusion case below (wontfix
    li-4x3a45, broadened 2026-07-04, see livespec `.ai/ci-gate-discipline.md`):
    this gate has NO escape lever, flag, or severity knob. "Cannot prove green"
    is a world-gate failure exactly as "known red" is, so it gets the same
    pin against a lever being quietly reintroduced.
    """
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        returncode=1,
        auth_returncode=0,
    )
    result = _run_check(
        cwd=tmp_path,
        env_path=fake_path,
        env_extra={"LIVESPEC_MASTER_CI_GREEN": "warn"},
    )
    assert result.returncode == 1
    assert "cannot prove master CI is green" in result.stderr


def test_unexpected_payload_shape(*, tmp_path: Path) -> None:
    """gh returns a non-object payload → exit 0 with error log."""
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout='["not an object"]')
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "unexpected gh response shape" in result.stderr


def test_check_runs_entry_not_dict(*, tmp_path: Path) -> None:
    """gh returns check_runs whose first entry isn't a dict → exit 0 with error log."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"total_count": 1, "check_runs": ["not a dict"]}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "unexpected ci-green check-run shape" in result.stderr


def test_missing_status_and_conclusion(*, tmp_path: Path) -> None:
    """gh returns a check run without status/conclusion fields → exit 0 with warning."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"total_count": 1, "check_runs": [{}]}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    # status is None (not in PENDING set) and conclusion is None
    # (not in GREEN or RED set), so falls through to "unrecognized" warning.
    assert "unrecognized conclusion" in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly via importlib (covers __name__ != "__main__" branch)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "master_ci_green_for_import_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing when _VENDOR_DIR is already on sys.path covers the False branch."""
    import importlib.util

    spec1 = importlib.util.spec_from_file_location(
        "master_ci_green_first_import",
        str(_CHECK),
    )
    assert spec1 is not None and spec1.loader is not None
    module1 = importlib.util.module_from_spec(spec1)
    spec1.loader.exec_module(module1)
    spec2 = importlib.util.spec_from_file_location(
        "master_ci_green_second_import",
        str(_CHECK),
    )
    assert spec2 is not None and spec2.loader is not None
    module2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(module2)
    assert callable(module2.main)
