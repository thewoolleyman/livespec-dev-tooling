"""Tests for dev-tooling/checks/no_fmt_directives.

The check bans formatter-suppression directives (`# fmt: off` /
`# fmt: on` / `# fmt: skip`) in the git-derived first-party `.py`
universe. Such directives suppress the formatter's honest
one-element-per-line expansion and are the mechanism of `file_lloc`
counter-shaving (packing `__all__`/collection entries onto fewer
physical lines to dodge the LLOC target).

Severity is controlled by the `LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST`
env lever ONLY (never run-vs-skip): unset → WARN / exit 0 (Phase-0
newly-covered propagation); set → ERROR / exit 1. Vendored, test-tree,
`templates/`, and `@generated`-marked files are outside the universe and
are never flagged, armed or not.

The fixtures are real git repos (`git init` + `git add`) because the
check derives its universe from `git ls-files` via
`resolve_check_universe`. That `git` spawn STAYS — it is the behaviour
the fixture exists to produce, and an in-process stand-in would leave the
check with an empty universe and every fixture passing vacuously. Its
hardcoded 3-key env is a REPLACEMENT rather than a filtered copy of
`os.environ`, so `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach
that child, which is the standing requirement on an allowlisted spawn and
why this file KEEPS its `subprocess_spawn_allowlist` entry.

The CHECK, by contrast, is now driven IN-PROCESS
(`monkeypatch.chdir(...)` + `capsys` + `rc = main()`) rather than as a
`sys.executable` subprocess: no `COVERAGE_PROCESS_START`-instrumented
child, no `.coverage.*` race under the parallel dispatcher, and
materially faster. The note here used to say the check was spawned "so
coverage instruments it"; that is no longer true of this file and is
corrected rather than left to mislead the next reader — an in-process
`main()` is measured directly by the parent's coverage session.

The severity lever is still set DETERMINISTICALLY per test, now via
`monkeypatch.setenv` / `monkeypatch.delenv` in this process rather than
an `env=` mapping on a child: the ambient value is dropped and the lever
armed only when the test asks, so severity never depends on the shell or
CI that runs the suite. `main()` reads it through `os.environ`, which the
monkeypatched process environment supplies unchanged.

Branch parity with the retired spawn: the same fixtures drive the same
arms — `# fmt: off` / `# fmt: on` / `# fmt: skip` detection, the unarmed
WARN/exit-0 and armed ERROR/exit-1 severities, and the vendored,
test-tree, `templates/` and `@generated` exclusions. The two lines the
child reached that an in-process call cannot are the module's
vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__": raise SystemExit(main())` line; both are
already excluded repo-wide by the PRE-EXISTING `exclude_also` patterns in
`[tool.coverage.report]`, so neither was ever measured here and no new
exclusion is introduced.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

from tests.livespec_dev_tooling.checks.config_parse_rendering import (
    assert_main_renders_the_parse_failure,
)

__all__: list[str] = []


_CHECK_PATH = (
    Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "checks" / "no_fmt_directives.py"
)
_FAIL_ENV = "LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env.

    `git` is not a Python spawn, so `tests_no_subprocess_spawn` permits it;
    the env is a REPLACEMENT rather than a filtered copy of `os.environ`, so
    `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach this child.
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

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red-Green-Replay hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "no_fmt_directives_under_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
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
    armed: bool,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """Seed the git fixture, then invoke the check's `main()` in-process under `cwd`."""
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    # Set the lever DETERMINISTICALLY — drop any ambient value, then arm it
    # only when the test asks — so severity never depends on the shell/CI that
    # runs the suite. `monkeypatch` supplies in THIS process exactly what the
    # retired child's `env=` mapping supplied, and undoes it after the test.
    monkeypatch.delenv(_FAIL_ENV, raising=False)
    if armed:
        monkeypatch.setenv(_FAIL_ENV, "true")
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write(*, root: Path, rel: str, body: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")


# A first-party file (not `_vendor`, not `tests/`, not `templates/`, not
# `@generated`); its location no longer affects severity — the lever does.
_FIRST_PARTY_REL = "pkg/mod.py"


def test_fmt_off_unarmed_warns_exit_0(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `# fmt: off` with the lever UNSET → WARNING diagnostic, exit 0."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="# fmt: off\nfrom __future__ import annotations\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=False, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr
    assert _FIRST_PARTY_REL in result.stderr
    assert '"level": "warning"' in result.stderr
    assert '"newly_covered": true' in result.stderr


def test_fmt_skip_unarmed_warns_exit_0(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A trailing `# fmt: skip` with the lever UNSET → WARNING, exit 0."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="from __future__ import annotations\n\n_K = [1, 2, 3]  # fmt: skip\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=False, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr
    assert '"level": "warning"' in result.stderr
    assert '"directive": "# fmt: skip"' in result.stderr


def test_fmt_off_armed_errors_exit_1(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `# fmt: off` with the lever SET → ERROR diagnostic, exit 1."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="# fmt: off\nfrom __future__ import annotations\n\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, result.stderr
    assert _FIRST_PARTY_REL in result.stderr
    assert '"level": "error"' in result.stderr
    assert '"failing": true' in result.stderr


def test_armed_clean_file_exit_0(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A clean file with the lever SET → exit 0, no finding (armed-but-clean)."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body='"""A clean module."""\n\nfrom __future__ import annotations\n\n__all__: list[str] = []\n',
    )
    result = _run_check(cwd=tmp_path, armed=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_spacing_variants_all_match(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`# fmt: off`, `# fmt:off`, and `#fmt: off` all match (armed → exit 1)."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body=(
            "# fmt: off\n"
            "from __future__ import annotations\n"
            "# fmt:off\n"
            "_A = 1\n"
            "#fmt: off\n"
            "_B = 2\n"
            "\n"
            "__all__: list[str] = []\n"
        ),
    )
    result = _run_check(cwd=tmp_path, armed=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 1, result.stderr
    assert '"directive": "# fmt: off"' in result.stderr
    assert '"directive": "# fmt:off"' in result.stderr
    assert '"directive": "#fmt: off"' in result.stderr


def test_benign_fmt_comment_does_not_match(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Comments that merely contain "fmt" (or `fmt: offset`) do NOT match, even armed → exit 0."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body=(
            "from __future__ import annotations\n"
            "\n"
            "# reformatting the fmt string happens later\n"
            "# fmt is a nice tool\n"
            "_OFFSET = 3  # fmt: offset = 3\n"
            "\n"
            "__all__: list[str] = []\n"
        ),
    )
    result = _run_check(cwd=tmp_path, armed=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_vendored_file_fmt_off_not_flagged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `# fmt: off` inside a `_vendor/` file is out of the universe (armed → exit 0)."""
    _write(
        root=tmp_path,
        rel=".claude-plugin/scripts/_vendor/upstream/shipped.py",
        body="# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_generated_file_fmt_off_not_flagged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An `@generated`-marked file's `# fmt: off` is out of the universe (armed → exit 0)."""
    _write(
        root=tmp_path,
        rel=_FIRST_PARTY_REL,
        body="# @generated\n# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_test_tree_file_fmt_off_not_flagged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `# fmt: off` inside the configured test tree is out of the universe (armed → exit 0)."""
    _write(
        root=tmp_path,
        rel="tests/test_something.py",
        body="# fmt: off\n__all__: list[str] = []\n",
    )
    result = _run_check(cwd=tmp_path, armed=True, monkeypatch=monkeypatch, capsys=capsys)
    assert result.returncode == 0, result.stderr
    assert "no-fmt-directives" not in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main().

    Exercises the false arms of (a) the vendor `sys.path` guard at
    module-load time and (b) the `if __name__ == "__main__"` guard at the
    bottom — both untaken under subprocess invocation. Mirrors the pattern
    in `test_comment_line_anchors`.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_fmt_directives_for_import_test",
        str(_CHECK_PATH),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_main_renders_the_consumer_config_parse_failure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed consumer config is a structured diagnostic, never a traceback.

    Same transitive reach as `file_lloc`: this check never names `load_config`,
    it calls `resolve_check_universe`, which parses the consumer config itself.
    So it escaped both the original "30 of 31" measurement and the repo-wide
    scan the first sweep of `livespec-dev-tooling-efxa` added.

    The non-zero here is UNCONDITIONAL, and deliberately not the check's
    `_EXIT_VIOLATIONS`. This is a Phase-0 warn check whose findings exit 0
    until `LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST` arms them — but that lever
    scopes the directives this check FINDS, never a consumer config it could
    not read at all, so an unparseable config fails whether or not the lever
    is set. This test runs with the lever unset to pin exactly that.
    """
    monkeypatch.delenv(_FAIL_ENV, raising=False)
    assert_main_renders_the_parse_failure(
        module_slug="no_fmt_directives",
        check_id="no-fmt-directives",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
