"""Outside-in test for `dev-tooling/checks/no_raise_outside_io.py` — domain-error raises confined to io/+errors.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-no-raise-outside-io` row), raising
of `LivespecError` subclasses (domain errors) at runtime is
restricted to `livespec/io/**` and `livespec/errors.py`.
Anywhere else under `livespec/**`, raising domain errors is
banned — pure layers return `Failure(LivespecError(...))` on
the ROP railway. Raising bug-class exceptions (TypeError,
NotImplementedError, AssertionError, etc.) is permitted
anywhere.

The known domain-error class names that count as
`LivespecError` subclasses: `LivespecError` itself,
`UsageError`, `PreconditionError`, `ValidationError`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_NO_RAISE_OUTSIDE_IO = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "no_raise_outside_io.py"


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env (no os.environ)."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it.

    The check derives its universe from the git INDEX, so a fixture that is
    not a git repo has no universe at all, and an untracked file is invisible.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def _run(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    """`git init` + stage the fixture, then run the check as a consumer would."""
    _init_repo_with_files(tmp_path=cwd)
    return subprocess.run(
        [sys.executable, str(_NO_RAISE_OUTSIDE_IO)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_raise_outside_io_rejects_domain_error_raise_in_pure_layer(*, tmp_path: Path) -> None:
    """A `raise ValidationError(...)` inside `livespec/parse/foo.py` fails the check.

    Fixture: a parse-layer module raises a domain error (banned
    — pure layers return Failure(...) on the railway). The
    check must walk livespec/, parse the file, detect the
    domain-error raise, exit non-zero, and surface the file
    path plus line number.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def parse_thing() -> None:\n"
        '    raise ValidationError("malformed")\n',
        encoding="utf-8",
    )

    result = _run(cwd=tmp_path)

    assert result.returncode != 0, (
        f"no_raise_outside_io should reject ValidationError raise in parse/; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/parse/foo.py"
    assert expected_path in combined, (
        f"no_raise_outside_io diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_domain_error_raise_in_io_layer(*, tmp_path: Path) -> None:
    """A `raise PreconditionError(...)` inside `livespec/io/fs.py` passes (exit 0).

    Pass-case: the io/ layer is the side-effect boundary that
    legitimately raises domain errors (the impure_safe
    decorator lifts them onto the IOResult railway via
    @impure_safe(exceptions=(PreconditionError,)).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "io"
    package_dir.mkdir(parents=True)
    source = package_dir / "fs.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def read_text() -> None:\n"
        '    raise PreconditionError("missing")\n',
        encoding="utf-8",
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept domain-error raise in io/ with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_domain_error_raise_in_errors_module(*, tmp_path: Path) -> None:
    """A `raise LivespecError(...)` inside `livespec/errors.py` passes (exit 0).

    Pass-case: errors.py is the hierarchy definition module
    and is exempt by spec.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec"
    package_dir.mkdir(parents=True)
    source = package_dir / "errors.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def raise_test() -> None:\n"
        '    raise LivespecError("test")\n',
        encoding="utf-8",
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept domain-error raise in errors.py with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_bug_class_raise_in_pure_layer(*, tmp_path: Path) -> None:
    """A `raise TypeError(...)` (bug-class) in pure layer passes (exit 0).

    Pass-case: bug-class exceptions (TypeError, ValueError,
    NotImplementedError, AssertionError, etc.) are permitted
    anywhere — they propagate to the supervisor's bug-catcher.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def parse_thing() -> None:\n"
        '    raise NotImplementedError("not yet")\n'
        "\n"
        "\n"
        "def reraise() -> None:\n"
        "    try:\n"
        "        parse_thing()\n"
        "    except NotImplementedError:\n"
        "        raise\n",
        encoding="utf-8",
    )

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept bug-class raise with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_accepts_a_codeless_repo(*, tmp_path: Path) -> None:
    """A genuinely codeless repo (0 tracked first-party `.py`) passes with exit 0.

    Replaces a test that asserted a declared source tree containing no Python
    is a misdeclaration. That was the `source_trees_exit_code` role-key gate,
    which this check no longer consults — the universe comes from the git
    index now, so "declared a tree with nothing in it" is not a state this
    check can observe.

    What replaces it is the distinction that still matters and is easy to get
    wrong: an EMPTY universe must be a PASS, not a configuration error. It is
    the one exemption the railway clause grants — a governed repo with zero
    first-party Python — and `livespec-console-beads-fabro` is the verified
    fleet case. Failing closed here would redden a conforming repo.
    """
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run(cwd=tmp_path)

    assert result.returncode == 0, (
        f"no_raise_outside_io should accept a codeless repo with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_no_raise_outside_io_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_raise_outside_io_for_import_test",
        str(_NO_RAISE_OUTSIDE_IO),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_no_raise_outside_io_covers_a_tracked_file_with_source_trees_declared_empty(
    *, tmp_path: Path
) -> None:
    """`source_trees = []` must NOT mean "scan nothing" — the scope dodge is closed.

    This is the invariant `livespec-dev-tooling-i532` exists for. Under the
    allowlist universe a repo could disarm the Result-railway checks over its
    whole package by declaring one empty array, and the declaration read as
    conformance: `source_trees_exit_code` treated declared-empty as a
    sanctioned opt-out and returned 0 before inspecting anything.

    A git-derived universe removes the lever entirely. The file below is
    tracked and first-party, so it is covered, and NO declaration names it —
    which is the other half of the acceptance: a newly-tracked first-party
    `.py` is covered the moment it is tracked, with nothing to declare and
    nothing to forget.

    `io_trees` is deliberately still declared here and still empty: it remains
    a genuine architectural role key, and declaring it empty must go on meaning
    "nothing is wholesale exempt", never "inspect nothing".
    """
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\n" "source_trees = []\n" "io_trees = []\n",
        encoding="utf-8",
    )
    package_dir = tmp_path / "pkg"
    package_dir.mkdir(parents=True)
    _ = (package_dir / "undeclared.py").write_text(
        "from __future__ import annotations\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def parse_thing() -> None:\n"
        '    raise ValidationError("malformed")\n',
        encoding="utf-8",
    )
    _init_repo_with_files(tmp_path=tmp_path)

    result = _run(cwd=tmp_path)

    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        f"no_raise_outside_io must inspect a tracked first-party file even with "
        f"`source_trees = []`; got returncode={result.returncode} combined={combined!r}"
    )
    assert (
        "pkg/undeclared.py" in combined
    ), f"the diagnostic must name the undeclared-but-tracked offender; combined={combined!r}"
