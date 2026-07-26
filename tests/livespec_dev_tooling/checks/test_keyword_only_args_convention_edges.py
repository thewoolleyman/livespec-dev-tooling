"""Edge arcs of the externally-fixed-calling-convention exemption.

Companion to `test_keyword_only_args.py`, which owns the six behaviours the
exemption exists for (livespec-dev-tooling-2prg). THIS module owns the shapes that
must NOT be mistaken for evidence — the negative space around the carve-out.

Each test here pins one way a lookalike could widen the exemption by accident:
an import that is not from the stdlib, a substitution target that is not a plain
name chain, and a substituted value that is neither a function reference nor a
factory. A carve-out that quietly accepted any of these would stop being derived
from real evidence and start being a general escape hatch, which is precisely what
`overseer-bg2.9` forbids.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from livespec_dev_tooling.checks.keyword_only_args import main

__all__: list[str] = []


@dataclass(frozen=True, kw_only=True, slots=True)
class _CheckRun:
    """What one in-process check invocation produced."""

    returncode: int
    stdout: str
    stderr: str


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


def _run_check(
    *,
    cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _CheckRun:
    """`git init` + stage the fixture, then call `main()` IN-PROCESS.

    The check derives its universe from the git index, so the fixture still needs a
    real `git`; but the check itself is a plain function call. Spawning a Python
    child would race `COVERAGE_PROCESS_START` and is banned by
    `check-tests-no-subprocess-spawn`.
    """
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    returncode = main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=returncode, stdout=captured.out, stderr=captured.err)


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def test_a_non_stdlib_from_import_binds_no_externally_owned_name(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`from mypkg import Thing` does NOT make `Thing` an externally-owned name (exit 1).

    Only a `from`-import whose ROOT module is stdlib binds a name whose calling
    convention this repo does not control. A first-party import must not be
    mistaken for one, or every locally-imported name becomes an exemption key.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "from mypkg import Thing\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def _install(*, mod, monkeypatch) -> None:\n"
            "    def _double(arg):\n"
            "        return Thing(arg)\n"
            "\n"
            "    monkeypatch.setattr(mod, 'Thing', _double)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a non-stdlib `from` import must not bind an externally-owned name; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "_double" in result.stdout + result.stderr, (
        f"diagnostic does not name the offending double `_double`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_a_computed_substitution_target_is_not_evidence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`setattr(factory().mod, "run", d)` is not evidence of stdlib ownership (exit 1).

    The target must be a plain dotted name for its components to be testable
    against the stdlib module set. A call in the chain means the target is decided
    at runtime, and a check cannot claim to know what it resolves to.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def _install(*, factory, monkeypatch) -> None:\n"
            "    def _double(argv):\n"
            "        return argv\n"
            "\n"
            "    monkeypatch.setattr(factory().mod, 'launch', _double)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a computed substitution target must not be read as stdlib evidence; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_a_bound_method_substitute_exempts_nothing_by_name(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`setattr(os, "fsync", obj.method)` exempts no local `def` (exit 1).

    The substituted value is an attribute reference, not a name this file defines,
    so there is no local definition the evidence points at. An unrelated positional
    `def` in the same file must still fail — the carve-out is per-binding, not
    per-file.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "import os\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def unrelated(x: int) -> int:\n"
            "    return x\n"
            "\n"
            "\n"
            "def _install(*, obj, monkeypatch) -> None:\n"
            "    monkeypatch.setattr(os, 'fsync', obj.method)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"an attribute-valued substitute must not exempt unrelated defs in the file; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "unrelated" in result.stdout + result.stderr, (
        f"diagnostic does not name the offending function `unrelated`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_a_factory_lambda_constructing_nothing_exempts_no_class(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`setattr(os, "fsync", lambda: 0)` names no stand-in class (exit 1).

    A substituted lambda is treated as a factory only for the classes it actually
    constructs. One that constructs nothing must leave every class in the file
    still held to the rule.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "import os\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "class _Bystander:\n"
            "    def glob(self, _pattern):\n"
            "        return []\n"
            "\n"
            "\n"
            "def _install(*, monkeypatch) -> None:\n"
            "    monkeypatch.setattr(os, 'fsync', lambda: 0)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"a lambda constructing nothing must not exempt a bystander class's methods; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "glob" in result.stdout + result.stderr, (
        f"diagnostic does not name the offending method `glob`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_a_stdlib_module_name_as_the_substituted_attribute_is_evidence(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`setattr(mod, "subprocess", _double)` exempts `_double` (exit 0).

    A module can hold a stdlib MODULE under its own name, and substituting that is
    the documented way to make a patch land on the reader's own binding. The
    attribute is a stdlib module name, so the convention is still stdlib's.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def _install(*, mod, monkeypatch) -> None:\n"
            "    def _double(argv):\n"
            "        return argv\n"
            "\n"
            "    monkeypatch.setattr(mod, 'subprocess', _double)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"a stdlib module name as the substituted attribute should be evidence; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
