"""Outside-in test for `livespec_dev_tooling/no_direct_github_access.py`.

The Verifier half of the GitHub request-budget concern (work-item
livespec-dev-tooling-t2q4) bans direct GitHub access in first-party code and
points every convicted site at
`livespec_dev_tooling.budgeted_gh.gh_read`. This file drives the three control
families the work-item names, plus the two file-universe traps a 2026-08-08
prototype run measured:

- POSITIVE. A newly added direct `gh` argv, a urllib request naming the GitHub
  API host, and the SEPARATED-argv seam shape (`argv = ("gh", *args)` built on
  one line and spawned several lines down) each fail the check, and the
  diagnostic names the sanctioned client.
- NEGATIVE. Each exempt module passes, and the exemption is REPORTED with its
  reason rather than skipped silently.
- ANTI-VACUOUS. A run whose scope is empty FAILS rather than passing, and the
  scanned count is reported on every run.

The universe traps: a violation under a `_vendor/` segment must be invisible
(re-deriving a file set without that exclusion is what made vendoring
uncommittable before), and a docstring that merely NAMES the API host must not
be convicted (every module here documents its own forge posture).

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than through a `sys.executable` child: no
`COVERAGE_PROCESS_START`-instrumented subprocess, no `.coverage.*` race under
the parallel dispatcher, and materially faster.

The `git` spawn in `_git` STAYS, which is why this file carries a
`subprocess_spawn_allowlist` entry. The check resolves its file universe from
the git INDEX — that is precisely how the generated `mutants/` tree and the
rest of the gitignored scratch stay out of scope — so a real `git init` +
`git add -A` is the behaviour the fixture exists to produce. Replacing it with
a stubbed universe would be a test that no longer tests what it claims. Its
hardcoded 3-key env keeps `COVERAGE_PROCESS_START` / `COV_CORE_*` out of that
child, the standing requirement on an allowlisted spawn.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECK_PATH = _REPO_ROOT / "livespec_dev_tooling" / "no_direct_github_access.py"

# The two banned shapes, written as fixture SOURCE rather than as live calls.
# This file is under the test tree, which the first-party filter drops, so the
# strings below are never scanned by the check they describe.
_GH_ARGV_CALL = '    completed = subprocess.run(["gh", "api", "repos/o/r"], check=False)\n'
_API_HOST_CALL = '    request = urllib.request.Request("https://api.github.com/repos/o/r")\n'


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    `git` is not a Python spawn, so `tests_no_subprocess_spawn` permits it;
    the hardcoded env is a REPLACEMENT rather than a filtered copy of
    `os.environ`, so `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach this
    child, and the developer's own git config cannot reach the fixture.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.no_direct_github_access`)
    so the test exercises the on-disk module the Red-Green-Replay hook
    inspects, and so `main()` can be invoked in-process under a monkeypatched
    cwd.

    Registered in `sys.modules` BEFORE `exec_module`, the same way the
    `canonical_checks` and `canonical_recipe_fidelity` tests do it: under
    `from __future__ import annotations` the `@dataclass(kw_only=True)`
    decorator resolves `KW_ONLY` through `sys.modules[cls.__module__]`, which
    is `None` for a spec-loaded module that was never registered.
    """
    spec = importlib.util.spec_from_file_location(
        "no_direct_github_access_under_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_check_module()


class _CheckRun(NamedTuple):
    """In-process stand-in for the subprocess `CompletedProcess` shape."""

    returncode: int
    stdout: str
    stderr: str


def _seed(*, root: Path, rel: str, body: str) -> None:
    """Write `body` at `rel` under `root`, creating parent directories."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")


def _module_source(*, call_lines: str) -> str:
    """A minimal first-party module whose `read()` body carries `call_lines`."""
    return (
        "from __future__ import annotations\n"
        "\n"
        "import subprocess\n"
        "import urllib.request\n"
        "\n"
        '__all__: list[str] = ["read"]\n'
        "\n"
        "\n"
        "def read() -> object:\n" + call_lines + "    return completed\n"
    )


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """Seed the git fixture, then invoke the check's `main()` in-process under `cwd`."""
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def test_rejects_a_direct_gh_subprocess_argv(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `subprocess.run(["gh", ...])` call in first-party code fails the check.

    The POSITIVE control for shape 1. The diagnostic must name the offending
    file, its line, and the sanctioned client — a ban that does not say where
    to go instead leaves the caller with no remedy.
    """
    _seed(root=tmp_path, rel="pkg/reader.py", body=_module_source(call_lines=_GH_ARGV_CALL))

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"a direct `gh` argv must fail the check; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert (
        "pkg/reader.py" in combined
    ), f"diagnostic does not name the offending file `pkg/reader.py`; combined={combined!r}"
    assert _MODULE.SANCTIONED_CLIENT in combined, (
        f"diagnostic does not name the sanctioned client "
        f"`{_MODULE.SANCTIONED_CLIENT}`; combined={combined!r}"
    )


def test_rejects_a_urllib_request_naming_the_github_api_host(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A urllib request whose URL targets the GitHub API host fails the check.

    The POSITIVE control for shape 2 — the transport the `gh`-argv rule cannot
    see, because its target is a URL rather than an argv.
    """
    _seed(root=tmp_path, rel="pkg/reader.py", body=_module_source(call_lines=_API_HOST_CALL))

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"a urllib request to the GitHub API host must fail the check; "
        f"got returncode={result.returncode} combined={combined!r}"
    )
    assert (
        _MODULE.SANCTIONED_CLIENT in combined
    ), f"diagnostic does not name the sanctioned client; combined={combined!r}"


def test_rejects_the_separated_argv_runner_seam_shape(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An argv built on one line and spawned on another still fails the check.

    This repo's runner seams build `argv = ("gh", *args)` and spawn it several
    lines later behind a Protocol, so a matcher keyed on the CALL would see a
    variable and report nothing. Keying on the argv SEQUENCE is what makes the
    seam shape reachable.
    """
    _seed(
        root=tmp_path,
        rel="pkg/seam.py",
        body=(
            "from __future__ import annotations\n"
            "\n"
            "import subprocess\n"
            "\n"
            '__all__: list[str] = ["run_gh"]\n'
            "\n"
            "\n"
            "def run_gh(*, args: list[str]) -> object:\n"
            '    argv = ("gh", *args)\n'
            "    return subprocess.run(list(argv), check=False)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert (
        result.returncode != 0
    ), f"the separated-argv seam shape must fail the check; combined={combined!r}"
    assert (
        '"line": 9' in combined
    ), f"diagnostic does not report the argv line (9); combined={combined!r}"


def test_accepts_first_party_code_with_no_direct_github_access(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """First-party code that routes through the sanctioned client passes."""
    _seed(
        root=tmp_path,
        rel="pkg/reader.py",
        body=(
            "from __future__ import annotations\n"
            "\n"
            "from livespec_dev_tooling.budgeted_gh import gh_read\n"
            "\n"
            '__all__: list[str] = ["read"]\n'
            "\n"
            "\n"
            "def read() -> object:\n"
            '    return gh_read(args=["api", "repos/o/r"])\n'
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert (
        result.returncode == 0
    ), f"code routed through the sanctioned client must pass; combined={combined!r}"
    assert (
        '"scanned": 1' in combined
    ), f"the check must report the number of files it scanned; combined={combined!r}"


def test_fails_rather_than_passes_over_an_empty_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A run that scanned ZERO files FAILS — the anti-vacuous guard.

    Four checks in this suite have shipped green while scanning nothing.
    Emptiness is a defect in the scan, never a clean bill of health, so the
    zero-file run must be a failure carrying the scanned count.
    """
    _seed(root=tmp_path, rel="README.md", body="no python here\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"an empty scope must FAIL rather than pass; got returncode={result.returncode} "
        f"combined={combined!r}"
    )
    assert (
        '"scanned": 0' in combined
    ), f"the empty-scope failure must report the zero count; combined={combined!r}"


def test_exempt_modules_pass_and_their_exemption_is_reported(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every declared exemption passes, and each applied one is logged with its reason.

    The NEGATIVE control. An exemption is a documented severity lever, so the
    run that applies one must SAY so — a skip nobody can see in the output is
    the shape this registry exists not to be.
    """
    for exemption in _MODULE.EXEMPTIONS:
        _seed(root=tmp_path, rel=exemption.path, body=_module_source(call_lines=_GH_ARGV_CALL))

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert result.returncode == 0, (
        f"the exempt modules must pass; got returncode={result.returncode} "
        f"combined={combined!r}"
    )
    for exemption in _MODULE.EXEMPTIONS:
        assert exemption.path in combined, (
            f"the applied exemption for `{exemption.path}` is not reported; "
            f"combined={combined!r}"
        )
    assert '"excused_sites": 1' in combined, (
        f"the exemption report does not carry the number of sites it excused; "
        f"combined={combined!r}"
    )


def test_a_vendored_violation_is_outside_the_first_party_scope(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `_vendor/` path segment is excluded, so vendoring stays committable.

    This is how the concern's two remaining exemptions — the vendored budget
    client under `_vendor/livespec_runtime/github_budget*` and
    `livespec_runtime.github_auth.mint` — are realized: the suite's shared
    first-party filter drops them before the check opens a file. Three earlier
    checks re-derived their own file set without that exclusion and made
    vendoring uncommittable.
    """
    _seed(
        root=tmp_path,
        rel="pkg/_vendor/livespec_runtime/github_budget.py",
        body=_module_source(call_lines=_GH_ARGV_CALL),
    )
    _seed(root=tmp_path, rel="pkg/clean.py", body="__all__: list[str] = []\n")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert (
        result.returncode == 0
    ), f"a violation under a `_vendor` segment must be out of scope; combined={combined!r}"
    assert (
        '"scanned": 1' in combined
    ), f"the vendored file must not be counted as scanned; combined={combined!r}"


def test_prose_naming_the_api_host_is_not_a_call_site(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A docstring that NAMES the GitHub API host is not convicted.

    Every module in this package documents its own forge posture, and an
    exemption-by-documentation policy needs that rationale to stay writeable.
    """
    _seed(
        root=tmp_path,
        rel="pkg/documented.py",
        body=(
            '"""Reads nothing from api.github.com; the budgeted client does that."""\n'
            "\n"
            "from __future__ import annotations\n"
            "\n"
            '__all__: list[str] = ["read"]\n'
            "\n"
            "\n"
            "def read() -> str:\n"
            '    """Would talk to api.github.com if it talked to anything."""\n'
            '    return "nothing"\n'
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    combined = result.stdout + result.stderr
    assert (
        result.returncode == 0
    ), f"prose naming the API host must not be convicted; combined={combined!r}"


def test_scan_source_reports_line_and_shape_for_both_banned_forms() -> None:
    """`scan_source` is pure and reports each site's line plus which shape matched."""
    sites = _MODULE.scan_source(
        source=(
            "import subprocess\n"
            'argv = ["gh", "api"]\n'
            'url = "https://api.github.com/repos/o/r"\n'
        )
    )

    assert [(site.line, site.kind) for site in sites] == [
        (2, "gh-argv"),
        (3, "github-api-host"),
    ], f"scan_source did not report both shapes with their lines; got {sites!r}"


def test_scan_source_ignores_sequences_that_are_not_gh_argvs() -> None:
    """An empty sequence, a non-string head, and a non-`gh` head are all ignored.

    The three ways the argv rule must NOT fire. A matcher that convicted any
    list whose head happened to be dynamic would flag most of the package.
    """
    sites = _MODULE.scan_source(
        source=(
            "empty: list[str] = []\n"
            "dynamic = [binary, 'api']\n"
            "other = ('git', 'status')\n"
            "numeric = (1, 2)\n"
        )
    )

    assert sites == (), f"scan_source fired on a sequence that is not a `gh` argv; got {sites!r}"
