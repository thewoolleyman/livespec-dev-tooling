"""Outside-in test for `dev-tooling/checks/public_api_result_typed.py` — pure-layer public APIs are Result-typed.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-public-api-result-typed` row), every
public function (per `__all__` declaration) in pure layers
returns `Result` or `IOResult` per annotation OR carries a
railway-lifting decorator (`@impure_safe(...)` lifts to
`IOResult`, `@safe(...)` lifts to `Result`). Cycle 169
implements the minimum-viable subset: parse and validate
layers' public functions must be Result-typed or
@safe-decorated.

Documented exemptions (a-f per the canonical row) are NOT
yet implemented; subsequent cycles widen as concrete files
surface.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PUBLIC_API_RESULT_TYPED = (
    _REPO_ROOT / "livespec_dev_tooling" / "checks" / "public_api_result_typed.py"
)


def test_public_api_result_typed_rejects_non_result_public_function(*, tmp_path: Path) -> None:
    """A public function in `parse/` returning bare `int` (not Result) fails the check."""
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        '__all__: list[str] = ["compute"]\n'
        "\n"
        "\n"
        "def compute(*, x: int) -> int:\n"
        "    return x\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (
        f"public_api_result_typed should reject non-Result public; "
        f"got returncode={result.returncode}"
    )
    combined = result.stdout + result.stderr
    assert "compute" in combined, (
        f"diagnostic does not surface offending name `compute`; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_public_api_result_typed_accepts_result_typed_function(*, tmp_path: Path) -> None:
    """A public function returning `Result[...]` passes (exit 0)."""
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from returns.result import Result\n"
        "\n"
        '__all__: list[str] = ["compute"]\n'
        "\n"
        "\n"
        "def compute(*, x: int) -> Result[int, str]:\n"
        "    return Result.from_value(x)\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"public_api_result_typed should accept Result-typed public function; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_accepts_safe_decorated_function(*, tmp_path: Path) -> None:
    """A public function decorated with `@safe(...)` passes (exit 0).

    Fixture stacks a non-railway decorator BEFORE the
    `@safe(...)` to exercise the `for decorator in
    decorator_list:` loop continuation past a non-matching
    name (closes branch 89->88).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from functools import wraps\n"
        "from returns.result import safe\n"
        "\n"
        '__all__: list[str] = ["compute"]\n'
        "\n"
        "\n"
        "def passthrough(fn):\n"
        "    return fn\n"
        "\n"
        "\n"
        "@passthrough\n"
        "@safe(exceptions=(ValueError,))\n"
        "def compute(*, x: int) -> int:\n"
        "    return x\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"public_api_result_typed should accept @safe-decorated public function; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_skips_private_filename(*, tmp_path: Path) -> None:
    """A package-private module (`_*.py`) is wholly skipped.

    Closes the `if py_file.name.startswith("_"):` filename
    skip branch. The file's bare-int public function would
    otherwise fail; the filename skip protects it.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "_helpers.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        '__all__: list[str] = ["raw"]\n'
        "\n"
        "\n"
        "def raw(*, x: int) -> int:\n"
        "    return x\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"public_api_result_typed should skip _-prefixed filenames; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_skips_module_without_all(*, tmp_path: Path) -> None:
    """A module without `__all__` declaration has empty declared set; nothing surfaces.

    Closes the `_all_value_names` returns-empty-list branch.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "\n"
        "def compute(*, x: int) -> int:\n"
        "    return x\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"public_api_result_typed should skip modules without __all__; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_accepts_bare_safe_decorator(*, tmp_path: Path) -> None:
    """A `@safe` (bare, not Call form) decorator passes the check.

    Closes the `_decorator_terminal_name` non-Call branch
    (decorator IS a Name, not a Call).
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        "from returns.result import safe\n"
        "\n"
        '__all__: list[str] = ["compute"]\n'
        "\n"
        "\n"
        "@safe\n"
        "def compute(*, x: int) -> int:\n"
        "    return x\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"public_api_result_typed should accept bare @safe decorator; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_rejects_function_without_return_annotation(
    *,
    tmp_path: Path,
) -> None:
    """A public function without a return annotation fails the check.

    Closes the `if func.returns is None: return False` branch.
    """
    package_dir = tmp_path / ".claude-plugin" / "scripts" / "livespec" / "parse"
    package_dir.mkdir(parents=True)
    source = package_dir / "foo.py"
    source.write_text(
        "from __future__ import annotations\n"
        "\n"
        '__all__: list[str] = ["compute"]\n'
        "\n"
        "\n"
        "def compute(*, x):\n"  # No return annotation
        "    return x\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0, (
        f"public_api_result_typed should reject return-less function; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_ignores_private_function(*, tmp_path: Path) -> None:
    """A `_`-prefixed function is private and ignored by the check.

    Even if `_helper` returns `int` directly, it's not in
    `__all__`, so the check skips it.
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
        "def _helper(*, x: int) -> int:\n"
        "    return x\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        f"public_api_result_typed should ignore private function; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_rejects_declared_tree_with_no_python(*, tmp_path: Path) -> None:
    """A declared pure_trees path containing no Python files is a misdeclaration."""
    result = subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, (
        f"public_api_result_typed should reject a declared tree with no Python files; "
        f"got returncode={result.returncode}"
    )
    assert "declared role key resolves to no Python files" in result.stderr


def test_public_api_result_typed_module_importable_without_running_main() -> None:
    """The check module imports cleanly without invoking main()."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "public_api_result_typed_for_import_test",
        str(_PUBLIC_API_RESULT_TYPED),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main), "main should be importable without invocation"


_EXEMPT_TREES = (Path("commands"),)


def _offenders(*, body: str, rel: str = "commands/run.py") -> list[tuple[int, str]]:
    """Run the offender scan over `body` as if it lived at `rel`."""
    from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders

    return _find_offenders(source=body, rel_path=Path(rel), commands_trees=_EXEMPT_TREES)


def test_public_api_result_typed_exempts_any_function_returning_none() -> None:
    """`-> None` is exempt anywhere, per the ratified spec's own words.

    non-functional-requirements.md: "unless the function is a supervisor
    at a deliberate side-effect boundary (... or any function returning
    `None`)". The clause is NOT path-scoped, so it holds outside
    `commands/` too.
    """
    body = "__all__: list[str] = ['emit']\n\n\ndef emit(*, x: int) -> None:\n    return None\n"

    assert (
        _offenders(body=body, rel="livespec_dev_tooling/thing.py") == []
    ), "a public function returning None is exempt by the spec's own wording"


def test_public_api_result_typed_exempts_main_int_under_commands() -> None:
    """`main() -> int` in `commands/*.py` is the named supervisor exemption."""
    body = "__all__: list[str] = ['main']\n\n\ndef main() -> int:\n    return 0\n"

    assert _offenders(body=body) == [], "main() -> int under commands/ is exempt"


def test_public_api_result_typed_exempts_build_parser_under_commands() -> None:
    """`build_parser() -> ArgumentParser` in `commands/**.py` is exempt.

    Named ONLY by §"Typechecker rule set"; §"ROP composition" says the
    rule "exempts only such supervisors" and omits it. That conflict is
    filed as livespec-i04f. Implemented per the §Typechecker superset.
    """
    body = (
        "__all__: list[str] = ['build_parser']\n\n\n"
        "def build_parser() -> ArgumentParser:\n    return ArgumentParser()\n"
    )

    assert _offenders(body=body) == [], "build_parser() -> ArgumentParser under commands/ is exempt"


def test_public_api_result_typed_main_exemption_does_not_widen_outside_commands() -> None:
    """`main() -> int` OUTSIDE `commands/` is NOT exempt.

    The spec scopes this exemption to `commands/*.py` and
    `doctor/run_static.py`. A flat-layout repo declaring no commands
    tree therefore gets no main() exemption — implementing the scope
    literally rather than exempting every `main` everywhere.
    """
    body = "__all__: list[str] = ['main']\n\n\ndef main() -> int:\n    return 0\n"

    assert _offenders(body=body, rel="livespec_dev_tooling/thing.py") == [
        (4, "main")
    ], "main() -> int outside commands/ must stay flagged"


def test_public_api_result_typed_main_exemption_does_not_widen_to_other_returns() -> None:
    """`main() -> str` is not the named exemption; only `main() -> int` is."""
    body = "__all__: list[str] = ['main']\n\n\ndef main() -> str:\n    return ''\n"

    assert _offenders(body=body) == [(4, "main")], "only main() -> int is exempt, not main() -> str"


def test_public_api_result_typed_build_parser_exemption_does_not_widen() -> None:
    """`build_parser` outside `commands/` is NOT exempt."""
    body = (
        "__all__: list[str] = ['build_parser']\n\n\n"
        "def build_parser() -> ArgumentParser:\n    return ArgumentParser()\n"
    )

    assert _offenders(body=body, rel="livespec_dev_tooling/thing.py") == [
        (4, "build_parser")
    ], "build_parser outside commands/ must stay flagged"
