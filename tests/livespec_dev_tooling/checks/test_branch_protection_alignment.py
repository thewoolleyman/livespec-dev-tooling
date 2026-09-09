"""Outside-in test for `dev-tooling/checks/branch_protection_alignment.py`.

Guard Layer 1 mechanical check that prevents the v039-D1-style
drift between `.github/workflows/ci.yml`'s job matrix and the
default branch protection's required-checks list.

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than via a `sys.executable` subprocess: no
`COVERAGE_PROCESS_START`-instrumented child, no `.coverage.*` race under
the parallel dispatcher, and materially faster. `main()` reads
`Path.cwd()`, so the monkeypatched cwd anchors the fixture, and the
assertion targets are unchanged — the int exit code plus the structlog
stderr text, now read off `capsys` instead of `CompletedProcess`.

The `gh` / `git` stubs are UNAFFECTED: those are the check's OWN
subprocesses, and it finds them through `shutil.which` / `PATH` exactly
as before. What used to be the child's `env={**os.environ, "PATH": ...}`
is now `monkeypatch.setenv("PATH", ...)` in this process, which the
check's own children inherit identically.

Branch parity with the retired spawn: the graceful-absence exit, the
empty-matrix exit, the `gh`-unavailable skip, the protection-absent and
strict-enabled exits, and both alignment directions are driven by the
same fixtures as before, and the module-import pair below still covers
both arms of the vendored-path guard. The
`if __name__ == "__main__": raise SystemExit(main())` line is the one
line the child reached that an in-process call cannot; it is already
excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so it was never measured here and no new
exclusion is introduced.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "branch_protection_alignment.py"


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the
    test exercises the on-disk module the Red→Green hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    Registered in `sys.modules` before `exec_module` for the same reason
    `test_module_importable_without_running_main` does it: the dataclass
    machinery resolves string annotations via `sys.modules[cls.__module__]`.
    """
    module_name = "branch_protection_alignment_under_test"
    spec = importlib.util.spec_from_file_location(module_name, str(_CHECK))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _run_check(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    env_path: str | None = None,
) -> _CheckRun:
    """Run the check's `main()` in-process with cwd set to tmp_path (or any path).

    Overrides only PATH when `env_path` is given — the in-process
    equivalent of the retired child's `env={**os.environ, "PATH": ...}`,
    inherited by the `gh` / `git` subprocesses the check itself spawns.
    """
    monkeypatch.chdir(cwd)
    if env_path is not None:
        monkeypatch.setenv("PATH", env_path)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_missing_ci_yml_is_graceful(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Empty cwd → ci.yml missing → exit 0 (graceful absence-handling).

    Per epic li-univck Phase 1.1 (li-chkabs), every canonical check
    MUST exit 0 cleanly when its precondition is absent so the check
    is safe to wire universally across the fleet. Consumers that have
    not configured GitHub Actions CI have no `.github/workflows/ci.yml`;
    the branch-protection alignment invariant is vacuously satisfied.
    """
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 on missing ci.yml (graceful absence-handling); "
        f"got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_empty_matrix_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """ci.yml exists but has no parseable matrix → exit 1."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    _ = (workflows / "ci.yml").write_text("name: CI\non: push\n", encoding="utf-8")
    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, (
        f"expected exit 1 on empty matrix; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "matrix.target" in result.stderr


def test_gh_unavailable_skips_gracefully(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `gh` on PATH → exit 0 with a warning (local-dev tolerance)."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    ci_yml = textwrap.dedent("""\
        name: CI
        on: push
        jobs:
          check:
            strategy:
              matrix:
                target:
                  - check-foo
                  - check-bar
            runs-on: ubuntu-latest
        """)
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")
    # Empty PATH → gh CLI not found by shutil.which.
    result = _run_check(cwd=tmp_path, env_path="", monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 when gh unavailable; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "gh CLI not on PATH" in result.stderr


def test_real_repo_passes(
    *,
    tmp_path: Path,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Run the check against the real repo cwd; expect exit 0.

    With the path-portability refactor, the check resolves the
    target repository from `git remote get-url origin` rather than
    a hardcoded constant. Authenticated `gh` produces either pass
    (no missing-from-ci.yml) or warning-only output. With `gh`
    unauthenticated OR with no branch protection set on master,
    the check still exits 0 (graceful skip). Either way: exit 0.
    """
    result = _run_check(cwd=_REPO_ROOT, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 against real repo; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def _setup_repo_with_ci_yml(*, tmp_path: Path, matrix_targets: list[str]) -> None:
    """Write a synthetic ci.yml with the given matrix.target list."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    target_lines = "\n".join(f"          - {t}" for t in matrix_targets)
    ci_yml = (
        "name: CI\n"
        "on: push\n"
        "jobs:\n"
        "  check:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        f"{target_lines}\n"
        "    runs-on: ubuntu-latest\n"
    )
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")


def _checks_payload(*, contexts: list[object], strict: bool = False) -> str:
    """Serialize a `required_status_checks` object payload.

    The check reads the `repos/<owner>/<repo>/branches/<default-branch>/
    protection/required_status_checks` endpoint, which returns an OBJECT shaped
    `{"strict": <bool>, "contexts": [<str>, ...]}` — NOT the bare
    contexts list the older `/contexts` sub-endpoint returned. `strict`
    defaults to False because the strict-off merge-gate rule (livespec
    NFR section "CI as a merge gate (branch protection)") makes strict-off the
    only aligned state.
    """
    return json.dumps({"strict": strict, "contexts": contexts})


def _install_fake_gh(
    *,
    tmp_path: Path,
    stdout: str = '{"strict": false, "contexts": []}',
    stderr: str = "",
    returncode: int = 0,
    git_origin_url: str = "https://github.com/test-owner/test-repo.git",
    git_returncode: int = 0,
    git_head_ref: str | None = "refs/remotes/origin/master",
    repo_payload: str | None = None,
    enforce_admins_payload: str = '{"enabled": true}',
    enforce_admins_returncode: int = 0,
) -> str:
    """Install fake `gh` + `git` shell stubs at tmp_path/bin, return PATH including it.

    Both stubs are needed because the check resolves its target
    repository identifier from `git remote get-url origin` before
    invoking `gh api`. The git stub responds to `git remote get-url
    origin` with `git_origin_url` and the given `git_returncode`, and
    to `git symbolic-ref refs/remotes/origin/HEAD` with `git_head_ref`
    (None → exit 1, modeling an unset symref); every other git
    invocation exits 0 as a no-op so other code paths (e.g.,
    subprocess-cov instrumentation hooks) are unaffected.

    The gh stub appends each invocation's argv to `tmp_path/bin/gh.argv`
    (one line per call) so tests can assert which API paths were hit.
    When `repo_payload` is given, a `gh api repos/test-owner/test-repo`
    call answers with it (exit 0) — the default-branch API fallback —
    while every other call gets the canned `stdout`/`stderr`/
    `returncode`, mirroring real `gh api`, which on an error puts the
    JSON error body on stdout AND a human `gh: <message> (HTTP <code>)`
    line on stderr.

    The `.../protection/enforce_admins` sub-endpoint is dispatched
    SEPARATELY, with `enforce_admins_payload` / `enforce_admins_returncode`,
    because it is a second read against a different endpoint whose payload
    shape (`{"enabled": <bool>}`) is nothing like the
    `required_status_checks` object. Its default is the aligned state
    (`enabled: true`), so every fixture that is not about admin enforcement
    keeps producing exactly the findings it produced before the flag was
    read at all.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    gh_stderr_block = "" if not stderr else f"cat >&2 <<'STUB_ERR_EOF'\n{stderr}\nSTUB_ERR_EOF\n"
    repo_dispatch_block = (
        ""
        if repo_payload is None
        else (
            'if [ "$1" = "api" ] && [ "$2" = "repos/test-owner/test-repo" ]; then\n'
            f"cat <<'REPO_EOF'\n{repo_payload}\nREPO_EOF\n"
            "exit 0\n"
            "fi\n"
        )
    )
    enforce_admins_block = (
        'case "$2" in\n'
        "*/protection/enforce_admins)\n"
        f"cat <<'ADMINS_EOF'\n{enforce_admins_payload}\nADMINS_EOF\n"
        f"exit {enforce_admins_returncode}\n"
        ";;\n"
        "esac\n"
    )
    gh_script = (
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{bin_dir}/gh.argv'\n"
        f"{enforce_admins_block}"
        f"{repo_dispatch_block}"
        f"cat <<'STUB_EOF'\n{stdout}\nSTUB_EOF\n"
        f"{gh_stderr_block}"
        f"exit {returncode}\n"
    )
    _ = gh_path.write_text(gh_script, encoding="utf-8")
    gh_path.chmod(0o755)
    git_path = bin_dir / "git"
    head_ref_block = (
        'if [ "$1" = "symbolic-ref" ]; then\n  exit 1\nfi\n'
        if git_head_ref is None
        else (
            'if [ "$1" = "symbolic-ref" ]; then\n'
            f"  printf '%s\\n' '{git_head_ref}'\n"
            "  exit 0\n"
            "fi\n"
        )
    )
    git_script = (
        "#!/bin/sh\n"
        'if [ "$1" = "remote" ] && [ "$2" = "get-url" ] && [ "$3" = "origin" ]; then\n'
        f"  printf '%s\\n' '{git_origin_url}'\n"
        f"  exit {git_returncode}\n"
        "fi\n"
        f"{head_ref_block}"
        "exit 0\n"
    )
    _ = git_path.write_text(git_script, encoding="utf-8")
    git_path.chmod(0o755)
    return f"{bin_dir}:/usr/bin:/bin"


def _gh_argv_log(*, tmp_path: Path) -> str:
    """The fake gh stub's recorded argv lines (one invocation per line)."""
    return (tmp_path / "bin" / "gh.argv").read_text(encoding="utf-8")


def _setup_repo_with_gate_and_matrix(*, tmp_path: Path) -> None:
    """Write a ci.yml modeling the single-gate CI shape.

    A matrix job (`check-python`) whose legs report as
    `${{ matrix.target }}` — the templated `name:` `parse_ci_matrix`
    already covers — plus a top-level `ci-green` aggregate GATE job
    carrying a literal `name: ci-green`. Under the single-gate model,
    master branch protection requires ONLY the `ci-green` gate, a
    top-level job (not a matrix leg), so this is the fixture that
    exercises gate-job recognition.
    """
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    ci_yml = (
        "name: CI\n"
        "on: push\n"
        "jobs:\n"
        "  check-python:\n"
        "    name: ${{ matrix.target }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          - check-foo\n"
        "          - check-bar\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: run\n"
        "        run: echo hi\n"
        "  ci-green:\n"
        "    name: ci-green\n"
        "    needs: [check-python]\n"
        "    if: always()\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: report\n"
        "        run: echo ok\n"
    )
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")


def test_gate_job_recognized_as_required(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A required top-level GATE job (`ci-green`) is recognized, not flagged missing.

    Under the single-gate model, master branch protection requires only
    the `ci-green` aggregate gate — a TOP-LEVEL job (with `name: ci-green`),
    NOT a matrix leg — so `parse_ci_matrix` alone cannot see it. The
    alignment gate unions top-level jobs into the satisfied set, so it must
    NOT emit `required_check_missing_from_ci` and must exit 0 (protection
    present + strict off).
    """
    _setup_repo_with_gate_and_matrix(tmp_path=tmp_path)
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["ci-green"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 when the required check is the ci-green gate job; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "required_check_missing_from_ci" not in result.stderr
    assert "required check has no matching" not in result.stderr


def test_genuinely_missing_required_still_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A required check matching neither a matrix leg nor a top-level job → exit 4.

    Guards against over-broadening the gate-job recognition: `check-phantom`
    is not a matrix leg (`check-foo`/`check-bar`), not a top-level job id
    (`check-python`/`ci-green`), and not a literal `name:` (`ci-green`), so
    the union cannot rescue it and the check MUST still error exit 4. The
    recognized `ci-green` gate is NOT flagged (exactly one missing-check
    error is emitted).
    """
    _setup_repo_with_gate_and_matrix(tmp_path=tmp_path)
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["ci-green", "check-phantom"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when a genuinely-missing check is required; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "check-phantom" in result.stderr
    assert result.stderr.count("required_check_missing_from_ci") == 1, (
        f"only check-phantom should be flagged missing (ci-green is a "
        f"recognized gate job, not missing); stderr={result.stderr!r}"
    )


def test_parse_top_level_jobs_collects_ids_and_literal_names() -> None:
    """`parse_top_level_jobs` collects job ids + literal names and stops at column 0.

    Directly exercises the parser: it collects each 2-space job id
    (`build`, `matrix-job`) and each literal `name:` value (`ci-green`),
    SKIPS templated names (`${{ matrix.target }}`), does NOT match
    step-level `- name:` lines, and stops scanning at the next column-0
    key (`permissions:`) so nested keys under it (`contents:`) are not
    collected as jobs.
    """
    from livespec_dev_tooling.checks._ci_job_names import (
        parse_top_level_jobs,
    )

    source = (
        "name: CI\n"
        "on: push\n"
        "jobs:\n"
        "  build:\n"
        "    name: ci-green\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: a-step\n"
        "        run: echo hi\n"
        "  matrix-job:\n"
        "    name: ${{ matrix.target }}\n"
        "permissions:\n"
        "  contents: read\n"
    )
    result = parse_top_level_jobs(source=source)
    assert result == {"build", "ci-green", "matrix-job"}, result


def test_required_missing_from_ci_yml_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Required check absent from ci.yml matrix → exit 4 (check failed).

    Exit 4 is the documented "check failed (structured findings on
    stderr)" code (SPECIFICATION/contracts.md section "Exit-code table"),
    shared with the new protection-absent fail branch and with the
    sibling CI-alignment checks (`no_stale_revise_branches`,
    `primary_checkout_commit_refuse_hook_installed`).
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo", "check-missing"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when required check missing from ci.yml; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "check-missing" in result.stderr
    assert "required check has no matching ci.yml job" in result.stderr
    assert "required_check_missing_from_ci" in result.stderr


def test_aligned_lists_pass(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Required list and ci.yml matrix match exactly → exit 0, no warnings.

    The protection-present + aligned case: the API succeeds and the
    required-checks list matches the ci.yml matrix exactly, so neither
    the protection-absent fail branch nor the alignment fail branch
    fires.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo", "check-bar"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo", "check-bar"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    assert "required check has no matching" not in result.stderr
    assert "no branch protection" not in result.stderr
    assert "strict" not in result.stderr


def test_strict_enabled_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Protection present with required_status_checks.strict TRUE → exit 4.

    Strict (require-branches-up-to-date) MUST be OFF per livespec
    NFR section "CI as a merge gate (branch protection)": strict makes GitHub
    keep a behind PR current by merging master into its branch,
    injecting a `Merge branch 'master'` commit that violates
    required_linear_history and buries the Red-Green-Replay TDD
    trailers. The check FAILS (exit 4) with a structured `fail` finding
    (failure_mode strict_enabled). The matrix is otherwise aligned, so
    only the strict assertion fires.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"], strict=True),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when strict is enabled; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "strict_enabled" in result.stderr
    assert "strict" in result.stderr


def test_enforce_admins_disabled_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Protection present with `enforce_admins` DISABLED → exit 4.

    `enforce_admins` MUST be enabled per livespec
    `SPECIFICATION/non-functional-requirements.md` section "CI as a merge gate
    (branch protection)": with it off, an admin merges straight past a red
    required check and the whole merge gate is advisory for exactly the
    accounts that do the merging. The matrix is otherwise aligned and
    `strict` is off, so this fixture isolates the admin-enforcement
    assertion (livespec-dev-tooling-65c).
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        enforce_admins_payload='{"enabled": false}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when enforce_admins is disabled; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "enforce_admins_disabled" in result.stderr
    assert "enforce_admins" in result.stderr


def test_enforce_admins_enabled_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Protection present with `enforce_admins` ENABLED → exit 0, no finding.

    The control half of the pair: a fix that flagged admin enforcement
    under BOTH payloads would not have read the flag at all. Also pins the
    endpoint the flag is read FROM — the `required_status_checks` object
    does not carry `enforce_admins`, so the check must issue a second read
    against the `.../protection/enforce_admins` sub-endpoint, and the gh
    argv log is the evidence that it did.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        enforce_admins_payload='{"enabled": true}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 when enforce_admins is enabled; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "enforce_admins" not in result.stderr
    argv_log = _gh_argv_log(tmp_path=tmp_path)
    assert "repos/test-owner/test-repo/branches/master/protection/enforce_admins" in argv_log


def test_enforce_admins_endpoint_error_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `enforce_admins` read ERRORS after the required-checks read succeeded → exit 4.

    This is NOT the ordinary can't-read case the check skips on. Reaching
    here means the required-checks read already succeeded, so the token
    demonstrably holds the admin scope both reads need; a failure on the
    second endpoint is anomalous, and reporting a green merge gate off a
    flag this run never saw would certify an invariant it did not verify.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        enforce_admins_payload='{"message": "Server Error", "status": "500"}',
        enforce_admins_returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when the enforce_admins read errors; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "enforce_admins_unreadable" in result.stderr


def test_enforce_admins_shapeless_payload_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `enforce_admins` payload parses to a non-object → exit 4 (unreadable).

    Pins the `isinstance(parsed, dict)` False branch: a successful call
    whose body is not the documented `{"enabled": <bool>}` object leaves
    the flag unread, which is the same answer as an errored call and MUST
    NOT be read as enabled.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        enforce_admins_payload='"not an object"',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 on a non-object enforce_admins payload; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "enforce_admins_unreadable" in result.stderr


def test_enforce_admins_non_bool_enabled_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The `enforce_admins` object carries no boolean `enabled` → exit 4 (unreadable).

    Pins the `isinstance(enabled, bool)` False branch. An object missing
    the key is the shape that would otherwise be read as falsy-and-
    therefore-disabled OR as truthy-and-therefore-enabled depending on the
    coercion used; it is neither, because nothing was read.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        enforce_admins_payload='{"url": "https://api.github.com/x"}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when enforce_admins carries no boolean `enabled`; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "enforce_admins_unreadable" in result.stderr


def test_protection_absent_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """API definitively reports master is unprotected → exit 4 (check failed).

    GitHub's branch-protection endpoints return the canonical
    `{"message": "Branch not protected", ..., "status": "404"}` body
    (and a `gh: Branch not protected (HTTP 404)` stderr line) ONLY when
    an admin-scoped token reads a genuinely unprotected branch. That is
    a definitive "absent" answer, so the check MUST fail rather than
    skip: an unprotected master lets PRs auto-merge before CI finishes
    and lets a red PR land. Cites the new merge-gate NFR.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=(
            '{"message": "Branch not protected", '
            '"documentation_url": "https://docs.github.com/rest", "status": "404"}'
        ),
        stderr="gh: Branch not protected (HTTP 404)",
        returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when master is definitively unprotected; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "no branch protection" in result.stderr
    assert "protection_absent" in result.stderr


def test_permission_error_skips_gracefully(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """API errors with a non-definitive 404 (no admin read access) → exit 0 skip.

    The default Actions `GITHUB_TOKEN` lacks the admin scope needed to
    READ branch protection; GitHub returns a generic `Not Found` /
    `Resource not accessible by integration` rather than the canonical
    `Branch not protected`. The check CANNOT distinguish "absent" from
    "can't-read" in this case, so it MUST skip (exit 0), not fail.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=(
            '{"message": "Resource not accessible by integration", '
            '"documentation_url": "https://docs.github.com/rest", "status": "403"}'
        ),
        stderr="gh: Resource not accessible by integration (HTTP 403)",
        returncode=1,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 when protection is unreadable (no admin scope); "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "cannot distinguish absent protection from missing read access" in result.stderr
    assert "no branch protection" not in result.stderr


def test_blank_and_comment_lines_in_matrix_are_skipped(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Blank lines and `# comment` lines within the matrix target bullets are skipped.

    Exercises the in-bullet-list `continue` branch in
    `parse_ci_matrix` so an author may insert blank lines or
    comments to group jobs without breaking the parser.
    """
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    ci_yml = (
        "name: CI\n"
        "on: push\n"
        "jobs:\n"
        "  check:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        target:\n"
        "          # a comment line\n"
        "          - check-foo\n"
        "\n"
        "          - check-bar\n"
        "    runs-on: ubuntu-latest\n"
    )
    _ = (workflows / "ci.yml").write_text(ci_yml, encoding="utf-8")
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo", "check-bar"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 with blank/comment lines in matrix; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "required check has no matching" not in result.stderr


def test_unrequired_leg_errors_under_the_many_contexts_model(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No required aggregate gate + an unrequired matrix leg → exit 4.

    The many-contexts half of the discriminating control pair for
    livespec-dev-tooling-e2wv. Every required context here is itself a
    matrix leg (`check-foo`), so NO required context is a top-level
    aggregate gate: the single-gate model is NOT in force, and nothing
    catches `check-extra` when it goes red — the leg is not required and
    there is no required aggregate to fail in its place. The "some jobs
    are intentionally optional" leniency is unsound under this
    configuration, so the leg MUST be an ERROR (exit 4), not a warning.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo", "check-extra"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 for an unrequired matrix leg with no required "
        f"aggregate gate; got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "check-extra" in result.stderr
    assert "unrequired_leg_without_aggregate_gate" in result.stderr


def test_unrequired_leg_warns_when_a_required_aggregate_gate_exists(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A required aggregate gate + unrequired matrix legs → warning, exit 0.

    The single-gate half of the discriminating control pair: master
    requires only the top-level `ci-green` aggregate, which fails when
    any leg does, so `check-foo`/`check-bar` being absent from the
    required list is genuinely benign. The new rule MUST stay quiet here
    — a fix that errors under BOTH models has not distinguished them.
    """
    _setup_repo_with_gate_and_matrix(tmp_path=tmp_path)
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["ci-green"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 when a required aggregate gate covers the "
        f"unrequired legs; got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "check-foo" in result.stderr
    assert "not in branch-protection required list" in result.stderr
    assert "unrequired_leg_without_aggregate_gate" not in result.stderr


def test_gh_api_failure_skips_gracefully(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """gh available but API call fails → exit 0 with warning."""
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout="error", returncode=1)
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    assert "gh api call failed" in result.stderr


def test_main_default_branch_resolved_from_git_symref(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A main-default repo's protection is read at `branches/main` (17o).

    The clone's `refs/remotes/origin/HEAD` symref points at
    `refs/remotes/origin/main`, so the check MUST query
    `branches/main/protection/...` — the historical hardcoded `master`
    path read the protection of a nonexistent branch on such a repo
    and misreported (livespec-dev-tooling-17o).
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        git_head_ref="refs/remotes/origin/main",
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 on an aligned main-default repo; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    argv_log = _gh_argv_log(tmp_path=tmp_path)
    assert "repos/test-owner/test-repo/branches/main/protection/required_status_checks" in argv_log
    assert "branches/master" not in argv_log


def test_default_branch_falls_back_to_repo_object_when_symref_unset(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Symref unset → the repo object's `default_branch` drives the path.

    A single-ref CI fetch has no `refs/remotes/origin/HEAD`; the check
    then reads `repos/<owner>/<repo>` (basic read access suffices) and
    uses its `default_branch` — here `main`.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        git_head_ref=None,
        repo_payload='{"default_branch": "main"}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 via the repo-object fallback; "
        f"got {result.returncode}, stderr={result.stderr!r}"
    )
    argv_log = _gh_argv_log(tmp_path=tmp_path)
    assert "branches/main/protection/required_status_checks" in argv_log
    assert "branches/master" not in argv_log


def test_default_branch_shapeless_repo_payload_falls_back_to_master(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Non-origin symref + non-object repo payload → `master` fallback (warn).

    The symref answers with a ref outside `refs/remotes/origin/` (so it
    is rejected) and the repo object parses to a non-dict, so neither
    resolver answers; the check warns and falls back to `master` —
    preserving the pre-17o behavior for unresolvable repos.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        git_head_ref="refs/heads/master",
        repo_payload='"not an object"',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    assert "could not resolve the default branch" in result.stderr
    argv_log = _gh_argv_log(tmp_path=tmp_path)
    assert "branches/master/protection/required_status_checks" in argv_log


def test_default_branch_non_string_in_repo_payload_falls_back_to_master(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Repo object without a usable `default_branch` string → `master` fallback."""
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo"]),
        git_head_ref=None,
        repo_payload='{"default_branch": 7}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    assert "could not resolve the default branch" in result.stderr
    argv_log = _gh_argv_log(tmp_path=tmp_path)
    assert "branches/master/protection/required_status_checks" in argv_log


def test_default_branch_api_failure_falls_back_to_master(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Symref unset + repo-object read fails → `master` fallback, then skip.

    Covers the api-resolver's non-zero-exit branch: with no
    `repo_payload` dispatch, the stub's canned failure answers the
    `repos/<owner>/<repo>` read too, so both resolvers miss, the check
    falls back to `master`, and the subsequent protection read fails
    non-definitively → graceful skip (exit 0).
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout="error",
        returncode=1,
        git_head_ref=None,
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    assert "could not resolve the default branch" in result.stderr
    assert "gh api call failed" in result.stderr


def test_git_remote_failure_skips_gracefully(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """git available but `git remote get-url origin` fails → exit 0 with warning.

    Closes the `completed.returncode != 0` branch of
    `_resolve_owner_repo`: a tmp_path that is not a git work tree
    (or any other condition that produces a non-zero git exit)
    MUST skip cleanly rather than fail the check.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(tmp_path=tmp_path, git_returncode=128)
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 when git remote fails; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "git remote get-url origin failed" in result.stderr


def test_non_github_remote_skips_gracefully(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """git returns a non-github.com remote URL → exit 0 with warning.

    Closes the `match is None` branch of `_resolve_owner_repo`:
    forks hosted on GitLab, self-hosted Gitea, mirrors, etc. fall
    outside this check's scope and MUST skip cleanly. Uses a
    gitlab.com URL as the canonical non-github example.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        git_origin_url="https://gitlab.com/some-org/some-repo.git",
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, (
        f"expected exit 0 on non-github remote; got {result.returncode}, "
        f"stderr={result.stderr!r}"
    )
    assert "origin URL did not match github.com pattern" in result.stderr


def test_unexpected_payload_shape(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """gh returns non-object payload → exit 0 with error log (no enforcement).

    The `required_status_checks` endpoint returns a JSON OBJECT; a bare
    JSON value that is not an object (here a string) has an unexpected
    shape and the check skips rather than enforces.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(tmp_path=tmp_path, stdout='"not an object"')
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0
    assert "unexpected gh api response shape" in result.stderr


def test_payload_with_non_string_entries(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """gh contexts list contains non-string entries → silently skip them (covers the False branch)."""
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout=_checks_payload(contexts=["check-foo", 42, None, "check-bar"]),
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    # Only "check-foo" and "check-bar" are extracted as required;
    # ci.yml has only "check-foo", so "check-bar" is missing → exit 4.
    assert result.returncode == 4
    assert "check-bar" in result.stderr


def test_payload_with_non_list_contexts(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`contexts` absent / not a list → treated as empty required set (covers the False branch).

    The `required_status_checks` object normally carries a `contexts`
    list, but a malformed payload may omit it or give it a non-list
    value. The check then treats the required-check set as EMPTY, which
    is the LIMIT CASE of the many-contexts exposure: with nothing
    required at all, no required context can be an aggregate gate, so
    `check-foo` is an unrequired leg that nothing catches → exit 4. This
    pins the `isinstance(contexts_raw, list)` False branch.
    """
    _setup_repo_with_ci_yml(tmp_path=tmp_path, matrix_targets=["check-foo"])
    fake_path = _install_fake_gh(
        tmp_path=tmp_path,
        stdout='{"strict": false}',
    )
    result = _run_check(cwd=tmp_path, env_path=fake_path, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 4, (
        f"expected exit 4 when contexts absent (empty required set leaves "
        f"the leg uncovered); got {result.returncode}, stderr={result.stderr!r}"
    )
    assert "unrequired_leg_without_aggregate_gate" in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly via importlib (covers __name__ != "__main__" branch)."""
    import importlib.util

    module_name = "branch_protection_alignment_for_import_test"
    spec = importlib.util.spec_from_file_location(module_name, str(_CHECK))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec_module so the module's
    # dataclasses can resolve string annotations under
    # `from __future__ import annotations` (the dataclass machinery
    # looks the module up via `sys.modules[cls.__module__]`).
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        assert callable(module.main)
    finally:
        sys.modules.pop(module_name, None)


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing the module when _VENDOR_DIR is already on sys.path covers the False branch."""
    import importlib.util

    # First import — primes sys.path with _VENDOR_DIR (True branch of the guard).
    name1 = "branch_protection_alignment_first_import"
    spec1 = importlib.util.spec_from_file_location(name1, str(_CHECK))
    assert spec1 is not None and spec1.loader is not None
    module1 = importlib.util.module_from_spec(spec1)
    sys.modules[name1] = module1
    try:
        spec1.loader.exec_module(module1)
        # Second import — _VENDOR_DIR is already on sys.path, exercises the False branch.
        name2 = "branch_protection_alignment_second_import"
        spec2 = importlib.util.spec_from_file_location(name2, str(_CHECK))
        assert spec2 is not None and spec2.loader is not None
        module2 = importlib.util.module_from_spec(spec2)
        sys.modules[name2] = module2
        try:
            spec2.loader.exec_module(module2)
            assert callable(module2.main)
        finally:
            sys.modules.pop(name2, None)
    finally:
        sys.modules.pop(name1, None)
