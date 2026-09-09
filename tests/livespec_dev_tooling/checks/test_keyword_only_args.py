"""Outside-in test for `livespec_dev_tooling/checks/keyword_only_args.py` — `*`-separator on every `def`.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-keyword-only-args` row), every `def` in
`livespec/**` uses `*` as the first separator (all parameters
keyword-only). Exempts Python-mandated dunder signatures, a
leading `self`/`cls`, and callables passed as `key=` to
`sorted`/`.sort()` (Python calls them positionally).

The check now resolves the files it inspects from the git-derived
first-party `.py` universe (`config.resolve_check_universe`),
root-anchored via `config.resolve_repo_root`, rather than a
`config.source_trees` walk — so each fixture is a real git repo
(`git init` + `git add -A`) before the check subprocess runs.
Phase-0 delta-WARN severity: `config.source_trees` is retained as
a classifier — a `def` missing the `*` separator in a
`source_trees` file keeps today's hard gate (`error`, exit 1); the
identical violation in a NEWLY-covered file emits at WARN
(`newly_covered` / `phase="0-warn"`, exit 0).

The check is driven IN-PROCESS (`monkeypatch.chdir(...)` + `capsys` +
`rc = main()`) rather than through a `sys.executable` subprocess: there is
no `COVERAGE_PROCESS_START`-instrumented child, so no per-fixture
`.coverage.*` data file is written and none can race under the parallel
dispatcher — and the fixture runs materially faster without an interpreter
start per case. `main()` anchors itself on `Path.cwd()`, so the
monkeypatched cwd places the fixture exactly where the child's `cwd=`
argument did, and every assertion target is unchanged: the same int exit
code and the same diagnostic text, now read off `capsys` rather than off a
`CompletedProcess`.

The `git` spawn in `_git` STAYS. This check resolves the files it inspects
from the git-derived first-party `.py` universe, so a real `git init` +
`git add -A` is the behaviour the fixture exists to produce; replacing it
would leave the git-index universe untested. Its hardcoded 3-key env keeps
`COVERAGE_PROCESS_START` / `COV_CORE_*` out of that child, which is the
standing requirement on an allowlisted spawn — so this file KEEPS its
`subprocess_spawn_allowlist` entry.

Branch parity with the retired spawn: the same fixtures drive the same
arms — the hard rejection of a positional-arg `def` inside `source_trees`;
the kw-only-separator, zero-arg, dunder, and `self`-then-kw-only
acceptances; the Phase-0 WARN-only newly-covered offender; the codeless
repo; the `sorted(key=)`, `.sort(key=)`, attribute-key, and
lambda-alongside-named-key sort-key carve-outs; and the five
externally-fixed-convention arms — a double for a stdlib module attr, for a
stdlib name held by a first-party module, for a stdlib module reached
through an attribute chain, a stand-in class's methods, and an argparse
`type=` callback — together with the load-bearing NEGATIVE arm that still
rejects a positional double of a first-party keyword-only function. The two
lines the child reached that an in-process call cannot are the module's
vendored-path guard (`sys.path.insert`) and its
`if __name__ == "__main__":` line; both are already excluded repo-wide by
the PRE-EXISTING `exclude_also` patterns in `[tool.coverage.report]`, so
neither was ever measured here and no new exclusion is introduced.
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


_REPO_ROOT = Path(__file__).resolve().parents[3]
_KEYWORD_ONLY_ARGS = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "keyword_only_args.py"

_POSITIONAL_ARG_SOURCE = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def fn(x: int) -> int:\n"
    "    return x\n"
)


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a `git` subcommand in `cwd` with a hermetic 3-key env (no os.environ).

    The env is a REPLACEMENT, not a filtered copy of `os.environ`, so
    `COVERAGE_PROCESS_START` / `COV_CORE_*` cannot reach this child and the
    developer's own git config cannot reach the fixture.
    """
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


def _init_repo_with_files(*, tmp_path: Path) -> None:
    """`git init` the fixture and stage every file already written under it."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def _load_check_module() -> ModuleType:
    """Import the check module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.checks...`) so the test
    exercises the on-disk module the Red-Green-Replay hook inspects, and so
    `main()` can be invoked in-process under a monkeypatched cwd.
    """
    spec = importlib.util.spec_from_file_location(
        "keyword_only_args_under_test",
        str(_KEYWORD_ONLY_ARGS),
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
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> _CheckRun:
    """`git init` + stage the fixture, then invoke the check's `main()` in-process."""
    _init_repo_with_files(tmp_path=cwd)
    monkeypatch.chdir(cwd)
    rc = _MODULE.main()
    captured = capsys.readouterr()
    return _CheckRun(returncode=rc, stdout=captured.out, stderr=captured.err)


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def test_keyword_only_args_rejects_def_with_positional_arg(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `def fn(x: int):` in a `source_trees` file fails hard (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_POSITIONAL_ARG_SOURCE,
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"keyword_only_args should reject positional arg with non-zero exit; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/livespec/foo.py"
    assert expected_path in combined, (
        f"keyword_only_args diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "fn" in combined, (
        f"keyword_only_args diagnostic does not surface offending function name `fn`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_def_with_kw_only_separator(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `def fn(*, x: int):` (kw-only separator present) passes the check (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def fn(*, x: int) -> int:\n"
            "    return x\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should accept kw-only def with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_zero_arg_def(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `def fn() -> int` (no args) passes the check (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def fn() -> int:\n"
            "    return 0\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should accept zero-arg def with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_dunder_methods(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dunder methods (`__init__`, `__repr__`, etc.) are exempt (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "class Foo:\n"
            "    def __init__(self, msg: str) -> None:\n"
            "        self.msg = msg\n"
            "\n"
            "    def __repr__(self) -> str:\n"
            '        return f"Foo({self.msg!r})"\n'
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt dunder methods with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_method_with_self_then_kw_only(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A method `def m(self, *, x: int)` (self + kw-only) passes (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "class Foo:\n"
            "    def m(self, *, x: int) -> int:\n"
            "        return x\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should accept self+kw-only method with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_warns_newly_covered_offender(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A positional-arg `def` OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_POSITIONAL_ARG_SOURCE)

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_keyword_only_args_accepts_codeless_repo(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should accept a codeless repo with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "keyword_only_args_for_import_test",
        str(_KEYWORD_ONLY_ARGS),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_keyword_only_args_accepts_sort_key_callable_in_sorted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A function used as `key=` in `sorted()` is exempt (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "items = [3, 1, 2]\n"
            "\n"
            "\n"
            "def _key(x: int) -> int:\n"
            "    return -x\n"
            "\n"
            "\n"
            "result = sorted(items, key=_key)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt sort key callable used in sorted(); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_sort_key_callable_in_list_sort(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A function used as `key=` in `.sort()` is exempt (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "items = [3, 1, 2]\n"
            "\n"
            "\n"
            "def _key(x: int) -> int:\n"
            "    return -x\n"
            "\n"
            "\n"
            "items.sort(key=_key)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt sort key callable used in list.sort(); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_attribute_sort_key_callable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A function used as `key=obj.method` (Attribute) in `sorted()` is exempt (exit 0).

    Also exercises a sort call with a non-key keyword (reverse=True) and a
    non-sort call (str(result)), covering the key-name collector branches.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "items = [3, 1, 2]\n"
            "\n"
            "\n"
            "def method(x: int) -> int:\n"
            "    return -x\n"
            "\n"
            "\n"
            "result = sorted(items, key=obj.method, reverse=True)\n"
            "other = str(result)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt attribute sort key callable; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_lambda_key_does_not_block_named_sort_key_carve_out(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A lambda `key=` does not interfere with the named-key carve-out (exit 0)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "items = [3, 1, 2]\n"
            "\n"
            "\n"
            "def _key(x: int) -> int:\n"
            "    return -x\n"
            "\n"
            "\n"
            "result = sorted(items, key=lambda x: -x)\n"
            "items.sort(key=_key)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should accept named sort-key callable used alongside a lambda key; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# --------------------------------------------------------------------------- #
# The externally-fixed calling convention exemption (livespec-dev-tooling-2prg).
#
# A callable BOUND AS A VALUE into a position whose calling convention is fixed
# OUTSIDE this repository cannot be made keyword-only without ceasing to be a
# substitute for the thing it stands in for. The evidence is derived from the
# consumer's own code, never declared: a `monkeypatch.setattr` against a
# stdlib-owned name, and an `argparse` `type=` callback.
#
# The NEGATIVE direction is the load-bearing half. Exempting every monkeypatched
# double would silently disarm the check against a double of the repo's OWN
# keyword-only function — a real defect found live in `livespec-overseer` while
# this exemption was being designed.
# --------------------------------------------------------------------------- #


def test_keyword_only_args_accepts_double_substituted_for_a_stdlib_module_attr(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`monkeypatch.setattr(os, "fsync", _boom)` exempts `_boom` (exit 0).

    `os.fsync(fd)` is called positionally by code this repo does not own, so a
    double taking `*, fd` is not a double of it.
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
            "def _install(*, monkeypatch) -> None:\n"
            "    def _boom(_fd):\n"
            "        raise OSError(28, 'No space left on device')\n"
            "\n"
            "    monkeypatch.setattr(os, 'fsync', _boom)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt a double substituted for a stdlib module attr; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_double_substituted_for_a_stdlib_name_on_a_first_party_module(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`monkeypatch.setattr(mymod, "Path", _redirect)` exempts `_redirect` (exit 0).

    The target module is first-party but the ATTRIBUTE is a stdlib name this file
    imports from `pathlib`, so the convention is still fixed elsewhere.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "from pathlib import Path\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def _install(*, mymod, monkeypatch) -> None:\n"
            "    def _redirect(arg):\n"
            "        return Path(str(arg))\n"
            "\n"
            "    monkeypatch.setattr(mymod, 'Path', _redirect)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt a double substituted for a stdlib name held by a "
        f"first-party module; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_double_substituted_via_an_attribute_chain_to_stdlib(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`monkeypatch.setattr(cfg.subprocess, "run", fake_run)` exempts `fake_run` (exit 0).

    Reaching the stdlib module THROUGH a first-party module is the documented way to
    make a patch land on the reader's own binding; the convention is still stdlib's.
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
            "def _install(*, cfg, monkeypatch) -> None:\n"
            "    def fake_run(argv, **_kwargs):\n"
            "        return argv\n"
            "\n"
            "    monkeypatch.setattr(cfg.subprocess, 'run', fake_run)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt a double reached through an attribute chain whose "
        f"last component is a stdlib module; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_still_rejects_a_double_of_a_first_party_keyword_only_function(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`monkeypatch.setattr(mod, "run_daemon", _fake_run)` STILL fails (exit 1).

    THE NEGATIVE DIRECTION. `run_daemon` is the repo's OWN function and is already
    keyword-only, so a positional double is a genuine defect, not an externally-fixed
    convention. An exemption keyed merely to "is monkeypatched" would swallow it —
    which is exactly what happened to one of the twelve `livespec-overseer` offenders
    this exemption was measured against.
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
            "    def _fake_run(warn_percent=None):\n"
            "        return warn_percent\n"
            "\n"
            "    monkeypatch.setattr(mod, 'run_daemon', _fake_run)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode != 0, (
        f"keyword_only_args must NOT exempt a double of a first-party function merely "
        f"because it is monkeypatched; got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "_fake_run" in result.stdout + result.stderr, (
        f"keyword_only_args diagnostic does not name the offending double `_fake_run`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_methods_of_a_class_standing_in_for_a_stdlib_name(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A stand-in class's methods are exempt when the class replaces a stdlib name (exit 0).

    `monkeypatch.setattr(mymod, "Path", lambda _p: _UnlistableDir())` makes
    `_UnlistableDir` a `Path` stand-in, so `glob(self, pattern)` implements a stdlib
    interface. The `TtyOut.write` bind-the-real-method trick cannot help here: the
    method must RAISE, so there is nothing to delegate to.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "from pathlib import Path\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def _install(*, mymod, monkeypatch) -> None:\n"
            "    class _UnlistableDir:\n"
            "        def glob(self, _pattern):\n"
            "            raise OSError(5, 'Input/output error')\n"
            "\n"
            "    monkeypatch.setattr(mymod, 'Path', lambda _path: _UnlistableDir())\n"
            "    assert Path\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt methods of a class standing in for a stdlib name; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_argparse_type_callback(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A function passed as `add_argument(..., type=_fn)` is exempt (exit 0).

    argparse calls its `type=` callback with one positional string. This is the same
    shape as the existing `sorted(key=...)` carve-out, from the same cause.
    """
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=(
            "from __future__ import annotations\n"
            "\n"
            "import argparse\n"
            "\n"
            "__all__: list[str] = []\n"
            "\n"
            "\n"
            "def _warn_percent(value: str) -> int:\n"
            "    return int(value)\n"
            "\n"
            "\n"
            "def build(*, parser: argparse.ArgumentParser) -> None:\n"
            "    parser.add_argument('--warn-percent', type=_warn_percent, default=None)\n"
        ),
    )

    result = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt an argparse `type=` callback; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_main_renders_the_consumer_config_parse_failure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A malformed consumer config is a structured diagnostic, never a traceback.

    `SPECIFICATION/contracts.md` section "Configuration loader" puts the catch
    at this check's `main()` supervisor; before `livespec-dev-tooling-efxa`
    the `ConfigParseError` escaped from here as an uncaught traceback, which
    reaches stderr through the interpreter rather than through structlog and
    so broke the very output discipline this package exists to enforce.
    """
    assert_main_renders_the_parse_failure(
        module_slug="keyword_only_args",
        check_id="keyword_only_args",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
