"""Outside-in test for `dev-tooling/checks/wrapper_shape.py` — `bin/*.py` 5-statement shebang-wrapper shape.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-wrapper-shape` row), every
`.claude-plugin/scripts/bin/*.py` file (except
`_bootstrap.py`) MUST conform to the 5-statement shebang-
wrapper shape (the shebang is a comment, not a Python
statement, and is not part of the AST body):

    #!/usr/bin/env python3
    \"\"\"Shebang wrapper for <name>. ...\"\"\"

    from _bootstrap import bootstrap

    bootstrap()

    from livespec.<...> import main

    raise SystemExit(main())

The AST body has exactly 5 top-level statements (the docstring
counts as an Expr): docstring + ImportFrom("_bootstrap") +
Expr(Call(bootstrap)) + ImportFrom("livespec.<...>") +
Raise(SystemExit(Call(main))).

Cycle 160 implements the structural check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_WRAPPER_SHAPE = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "wrapper_shape.py"


def test_wrapper_shape_rejects_wrapper_with_extra_statement(*, tmp_path: Path) -> None:
    """A wrapper with an extra top-level statement fails the check.

    Fixture: a bin/*.py wrapper with the canonical 5
    statements PLUS an additional `x = 1` statement. The
    check must walk bin/, parse the file, detect the
    deviation, exit non-zero, and surface the file path.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "seed.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Shebang wrapper for seed. No logic."""\n'
        "\n"
        "from _bootstrap import bootstrap\n"
        "\n"
        "bootstrap()\n"
        "\n"
        "from livespec.commands.seed import main\n"
        "\n"
        "x = 1  # extra statement — should fail\n"
        "\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (
        f"wrapper_shape should reject wrapper with extra statement; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    expected_path = ".claude-plugin/scripts/bin/seed.py"
    assert expected_path in combined, (
        f"wrapper_shape diagnostic does not surface offending file `{expected_path}`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_rejects_wrapper_with_wrong_statement_kind(*, tmp_path: Path) -> None:
    """A wrapper with 5 statements but wrong shape (statement 3 not bootstrap()) fails.

    Fixture: 5 statements but the third is `x = 1` (Assign,
    not Expr(Call(bootstrap))) and the fifth is `pass`
    (Pass, not Raise(SystemExit)). Closes the early-return
    False branches of `_is_bootstrap_call` and
    `_is_raise_systemexit_main`.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "seed.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Shebang wrapper for seed. No logic."""\n'
        "\n"
        "from _bootstrap import bootstrap\n"
        "\n"
        "x = 1\n"
        "\n"
        "from livespec.commands.seed import main\n"
        "\n"
        "pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (
        f"wrapper_shape should reject wrapper with wrong statement kinds; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_rejects_wrapper_with_wrong_final_statement(*, tmp_path: Path) -> None:
    """A wrapper with the first 4 statements correct but final not Raise fails.

    Fixture: 5 statements with the first 4 canonical, but the
    final is `pass` instead of `raise SystemExit(main())`.
    Closes the early-return False branch of
    `_is_raise_systemexit_main` after the short-circuit
    chain reaches it.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "seed.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Shebang wrapper for seed. No logic."""\n'
        "\n"
        "from _bootstrap import bootstrap\n"
        "\n"
        "bootstrap()\n"
        "\n"
        "from livespec.commands.seed import main\n"
        "\n"
        "pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (
        f"wrapper_shape should reject wrapper with wrong final statement; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_accepts_canonical_wrapper(*, tmp_path: Path) -> None:
    """A canonical 5-statement wrapper passes the check (exit 0)."""
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "seed.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Shebang wrapper for seed. No logic."""\n'
        "\n"
        "from _bootstrap import bootstrap\n"
        "\n"
        "bootstrap()\n"
        "\n"
        "from livespec.commands.seed import main\n"
        "\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"wrapper_shape should accept canonical wrapper with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_accepts_impl_plugin_family_wrapper(*, tmp_path: Path) -> None:
    """A canonical wrapper importing main from a `livespec_<suffix>` family package passes.

    Fixture: a bin/*.py wrapper that is canonical in every
    respect except the main-import module path is
    `livespec_impl_git_jsonl.commands.next` (the impl-plugin's
    own package name) rather than the core `livespec.` prefix.
    The check MUST accept any livespec-family top-level package
    (`livespec` or `livespec_<suffix>`), not just `livespec.`,
    so impl-plugin wrappers conforming to the canonical
    5-statement shape pass (li-ini4rz).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "next.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Shebang wrapper for next. No logic."""\n'
        "\n"
        "from _bootstrap import bootstrap\n"
        "\n"
        "bootstrap()\n"
        "\n"
        "from livespec_impl_git_jsonl.commands.next import main\n"
        "\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"wrapper_shape should accept a livespec-family impl-plugin wrapper with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_rejects_non_family_main_import(*, tmp_path: Path) -> None:
    """A wrapper whose main import is from a non-family package fails.

    Fixture: a wrapper canonical in every respect except the
    main-import module path is `os.path` (a clearly
    non-livespec-family top-level package). The relaxed
    family-prefix predicate must still reject module paths
    whose top-level package is neither `livespec` nor
    `livespec_<suffix>` (li-ini4rz).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "seed.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Shebang wrapper for seed. No logic."""\n'
        "\n"
        "from _bootstrap import bootstrap\n"
        "\n"
        "bootstrap()\n"
        "\n"
        "from os.path import main\n"
        "\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (
        f"wrapper_shape should reject a wrapper whose main import is from a "
        f"non-livespec-family package; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_rejects_lookalike_non_family_prefix(*, tmp_path: Path) -> None:
    """A wrapper importing from `livespecfoo.` (no separator) fails.

    Fixture: the main import is `livespecfoo.commands.seed` -
    a package whose name STARTS WITH the literal text
    `livespec` but is NOT a family member (the family rule
    requires either the bare `livespec` package or a
    `livespec_<suffix>` package, i.e. an underscore
    separator). This guards the relaxation against an
    over-broad `startswith("livespec")` regression (li-ini4rz).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "seed.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Shebang wrapper for seed. No logic."""\n'
        "\n"
        "from _bootstrap import bootstrap\n"
        "\n"
        "bootstrap()\n"
        "\n"
        "from livespecfoo.commands.seed import main\n"
        "\n"
        "raise SystemExit(main())\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (
        f"wrapper_shape should reject a wrapper importing from a livespec-lookalike "
        f"non-family package (`livespecfoo.`); "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_exempts_bootstrap_file(*, tmp_path: Path) -> None:
    """`bin/_bootstrap.py` is exempt from the wrapper-shape check.

    Pass-case: _bootstrap.py is the canonical exception to
    the wrapper shape per the canonical row's prose.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "bin"
    package_dir.mkdir(parents=True)
    source = package_dir / "_bootstrap.py"
    source.write_text(
        "#!/usr/bin/env python3\n"
        '"""Pre-livespec sys.path setup + Python version check."""\n'
        "from __future__ import annotations\n"
        "\n"
        "import sys\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def bootstrap() -> None:\n"
        "    if sys.version_info < (3, 10):\n"
        '        sys.stderr.write("python too old\\n")\n'
        "        raise SystemExit(127)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"wrapper_shape should exempt _bootstrap.py with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_accepts_empty_tree(*, tmp_path: Path) -> None:
    """An empty repo cwd passes the check (exit 0)."""
    result = subprocess.run(
        [sys.executable, str(_WRAPPER_SHAPE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"wrapper_shape should accept empty tree with exit 0; "
        f"got returncode={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_wrapper_shape_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "wrapper_shape_for_import_test",
        str(_WRAPPER_SHAPE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


def test_canonical_wrapper_stmt_count_pins_5() -> None:
    """The `_CANONICAL_WRAPPER_STMT_COUNT` constant pins the 5-statement shape.

    Per python-skill-script-style-requirements.md:
    every shebang wrapper has exactly five top-level statements
    (docstring → bootstrap import → bootstrap() call → main
    import → SystemExit(main())). This test pins the count so a
    future loosening requires explicit test failure + intentional
    bump.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "wrapper_shape_for_constant_test",
        str(_WRAPPER_SHAPE),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._CANONICAL_WRAPPER_STMT_COUNT == 5  # noqa: SLF001
