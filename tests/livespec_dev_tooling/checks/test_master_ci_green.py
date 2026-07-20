"""Outside-in test for `dev-tooling/checks/master_ci_green.py`.

Guard Layer 1 mechanical check that prevents the silent-red-master
pattern: master CI failed weeks ago, every PR merged onto red master
inherited the brokenness. The check ensures master CI is green at
every commit.

Three `gh` failure states are tested separately, because they do not
deserve the same answer. A host with no `gh` binary, and a host whose
`gh` holds no credential, were never able to check at all and skip
gracefully so local pre-commit is not blocked. A host whose `gh` IS
credentialed but whose API call failed attempted the check and got no
answer — it has not proven master is green, so it fails loudly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "master_ci_green.py"


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


def _install_fake_gh(
    *,
    tmp_path: Path,
    stdout: str = "[]",
    returncode: int = 0,
    auth_returncode: int = 0,
) -> str:
    """Install a fake `gh` shell stub at tmp_path/bin/gh, return PATH including it.

    The stub dispatches on the sub-command so the check's two distinct `gh`
    invocations can be driven independently:

    - `gh auth token` — the local credential probe. Exits `auth_returncode`
      (0 = a credential is stored, 1 = none), printing nothing, mirroring the
      real `gh` closely enough for the check while never emitting a token.
    - anything else (i.e. `gh run list ...`) — prints `stdout` and exits
      `returncode`.

    `auth_returncode` defaults to 0 because the credential probe only runs on
    the `gh run list` failure path, so a credentialed default leaves every
    happy-path test's behavior unchanged.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    script = (
        "#!/bin/sh\n"
        'if [ "$1" = "auth" ] && [ "$2" = "token" ]; then\n'
        f"  exit {auth_returncode}\n"
        "fi\n"
        f"cat <<'STUB_EOF'\n{stdout}\nSTUB_EOF\n"
        f"exit {returncode}\n"
    )
    _ = gh_path.write_text(script, encoding="utf-8")
    gh_path.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def test_success_conclusion_passes(*, tmp_path: Path) -> None:
    """Latest CI is success → exit 0."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='[{"status": "completed", "conclusion": "success"}]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0


def test_failure_conclusion_fails(*, tmp_path: Path) -> None:
    """Latest CI is failure → exit 1 with error diagnostic."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='[{"status": "completed", "conclusion": "failure"}]',
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
        stdout='[{"status": "completed", "conclusion": "failure"}]',
    )
    result = _run_check(
        cwd=tmp_path,
        env_path=fake_path,
        env_extra={"LIVESPEC_MASTER_CI_GREEN": "warn"},
    )
    assert result.returncode == 1
    assert "master CI is red" in result.stderr


def test_pending_status_passes(*, tmp_path: Path) -> None:
    """Latest CI still in_progress → exit 0 with info log."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='[{"status": "in_progress", "conclusion": null}]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "still pending" in result.stderr


def test_unrecognized_conclusion_passes(*, tmp_path: Path) -> None:
    """Unrecognized conclusion → exit 0 with warning (non-blocking)."""
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='[{"status": "completed", "conclusion": "neutral"}]',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "unrecognized conclusion" in result.stderr


def test_empty_runs_list_skips(*, tmp_path: Path) -> None:
    """No CI runs on master yet → exit 0 with warning."""
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout="[]")
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "no CI runs on master yet" in result.stderr


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
    """gh returns non-list payload → exit 0 with warning."""
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout='{"not": "a list"}')
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "no CI runs on master yet" in result.stderr


def test_first_entry_not_dict(*, tmp_path: Path) -> None:
    """gh returns list but first entry isn't a dict → exit 0 with error log."""
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout='["not a dict"]')
    result = _run_check(cwd=tmp_path, env_path=fake_path)
    assert result.returncode == 0
    assert "unexpected gh response shape" in result.stderr


def test_missing_status_and_conclusion(*, tmp_path: Path) -> None:
    """gh returns dict without status/conclusion fields → exit 0 with warning."""
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout="[{}]")
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
