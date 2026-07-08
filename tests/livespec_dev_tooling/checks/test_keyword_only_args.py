"""Outside-in test for `livespec_dev_tooling/checks/keyword_only_args.py` — `*`-separator on every `def`.

Per `python-skill-script-style-requirements.md` §"Canonical
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

The check is invoked as a `sys.executable` subprocess (this file is
in the documented `subprocess_spawn_allowlist`); pytest-cov's
pth-installed startup hook instruments the child.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
    """`git init` the fixture and stage every file already written under it."""
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["add", "-A"])


def _run_check(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    """`git init` + stage the fixture, then run the check as a consumer would."""
    _init_repo_with_files(tmp_path=cwd)
    return subprocess.run(
        [sys.executable, str(_KEYWORD_ONLY_ARGS)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def test_keyword_only_args_rejects_def_with_positional_arg(*, tmp_path: Path) -> None:
    """A `def fn(x: int):` in a `source_trees` file fails hard (exit 1)."""
    _write(
        tmp_path=tmp_path,
        rel_path=".claude-plugin/scripts/livespec/foo.py",
        source=_POSITIONAL_ARG_SOURCE,
    )

    result = _run_check(cwd=tmp_path)

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


def test_keyword_only_args_accepts_def_with_kw_only_separator(*, tmp_path: Path) -> None:
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should accept kw-only def with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_zero_arg_def(*, tmp_path: Path) -> None:
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should accept zero-arg def with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_dunder_methods(*, tmp_path: Path) -> None:
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt dunder methods with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_method_with_self_then_kw_only(*, tmp_path: Path) -> None:
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should accept self+kw-only method with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_warns_newly_covered_offender(*, tmp_path: Path) -> None:
    """A positional-arg `def` OUTSIDE `source_trees` WARNS (newly-covered), exit 0."""
    _write(tmp_path=tmp_path, rel_path="pkg/foo.py", source=_POSITIONAL_ARG_SOURCE)

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "pkg/foo.py" in combined
    assert "newly_covered" in combined
    assert '"level": "error"' not in combined


def test_keyword_only_args_accepts_codeless_repo(*, tmp_path: Path) -> None:
    """A genuinely codeless repo (0 first-party `.py`) passes (exit 0)."""
    _ = (tmp_path / "README.md").write_text("no code\n", encoding="utf-8")

    result = _run_check(cwd=tmp_path)

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


def test_keyword_only_args_accepts_sort_key_callable_in_sorted(*, tmp_path: Path) -> None:
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt sort key callable used in sorted(); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_sort_key_callable_in_list_sort(*, tmp_path: Path) -> None:
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt sort key callable used in list.sort(); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_accepts_attribute_sort_key_callable(*, tmp_path: Path) -> None:
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should exempt attribute sort key callable; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_keyword_only_args_lambda_key_does_not_block_named_sort_key_carve_out(
    *, tmp_path: Path
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"keyword_only_args should accept named sort-key callable used alongside a lambda key; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
