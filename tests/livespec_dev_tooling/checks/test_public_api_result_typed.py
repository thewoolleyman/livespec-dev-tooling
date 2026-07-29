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

import ast
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_PUBLIC_API_RESULT_TYPED = (
    _REPO_ROOT / "livespec_dev_tooling" / "checks" / "public_api_result_typed.py"
)
_PARSE_TREE = ".claude-plugin/scripts/livespec/parse"
_COMMANDS_TREE = ".claude-plugin/scripts/livespec/commands"


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


def _consume(*, tmp_path: Path, module: str, name: str) -> None:
    """Write a product module that imports `name` across a module boundary.

    Under ratified livespec v178 a function is public API only when CONSUMED
    ACROSS A BOUNDARY, so a fixture with no consumer asserts nothing about the
    Result-return rule: the check would exit 0 whatever the annotation says.
    Every fixture below that means to exercise the rule therefore ships a
    consumer, and the import is ABSOLUTE (`livespec.parse.<module>`) because
    that is how a layered consumer actually reaches a sibling.
    """
    consumer = tmp_path / _COMMANDS_TREE / "use.py"
    consumer.parent.mkdir(parents=True, exist_ok=True)
    _ = consumer.write_text(
        "from __future__ import annotations\n"
        "\n"
        f"from livespec.parse.{module} import {name}\n"
        "\n"
        "__all__: list[str] = []\n"
        "\n"
        "\n"
        "def run() -> None:\n"
        f"    _ = {name}(x=1)\n",
        encoding="utf-8",
    )


def _run_check(*, cwd: Path) -> subprocess.CompletedProcess[str]:
    """`git init` + stage the fixture, then run the check as a consumer would.

    The check resolves its consumption universe from the git-derived
    first-party set (`resolve_check_universe`), so a fixture must be a real
    git tree — the same fail-closed anchoring every applies-to-all check uses.
    """
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    return subprocess.run(
        [sys.executable, str(_PUBLIC_API_RESULT_TYPED)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def test_public_api_result_typed_rejects_non_result_public_function(*, tmp_path: Path) -> None:
    """A public function in `parse/` returning bare `int` (not Result) fails the check.

    The fixture RAISES, and that is load-bearing since livespec v179: the rule
    reaches a public function only when it HAS an expected failure mode, so a
    `return x` body would now be member-1 exempt and this test would assert the
    check rejects something the ratified rule no longer asks it to. The subject
    under test is the missing `Result`, and the raise is what keeps the
    function in scope for it.
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
        "def compute(*, x: int) -> int:\n"
        "    if x < 0:\n"
        "        raise ValueError(x)\n"
        "    return x\n",
        encoding="utf-8",
    )

    _consume(tmp_path=tmp_path, module="foo", name="compute")

    result = _run_check(cwd=tmp_path)

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

    _consume(tmp_path=tmp_path, module="foo", name="compute")

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"public_api_result_typed should accept Result-typed public function; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_accepts_safe_decorated_function(*, tmp_path: Path) -> None:
    """A public function decorated with `@safe(...)` passes (exit 0).

    The body RAISES so the DECORATOR is what makes this pass. Since livespec
    v179 a total body would be member-1 exempt, and the test would go green
    without the decorator branch ever running — passing for the wrong reason,
    which is the failure this suite exists to catch. The raise is also the
    honest fixture: `@safe(exceptions=(ValueError,))` exists to lift exactly
    this.

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
        "    if x < 0:\n"
        "        raise ValueError(x)\n"
        "    return x\n",
        encoding="utf-8",
    )

    _consume(tmp_path=tmp_path, module="foo", name="compute")

    result = _run_check(cwd=tmp_path)

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

    _consume(tmp_path=tmp_path, module="_helpers", name="raw")

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"public_api_result_typed should skip _-prefixed filenames; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_skips_module_without_all(*, tmp_path: Path) -> None:
    """A module with NEITHER an `__all__` nor a consumer is out of scope.

    This test used to close the `_all_value_names` empty-list branch. That
    function is gone: ratified livespec v178 replaced `__all__` membership with
    CONSUMED ACROSS A BOUNDARY, so the check no longer reads `__all__` to decide
    publicness at all. The assertion is retargeted rather than deleted, because
    what it now pins is still worth pinning — the RELAXING half, at integration
    tier. Its companion (a consumed function with NO `__all__` is still public,
    the anti-gaming half) lives in `test_public_api_criterion.py`, and the two
    must be read together: neither alone shows the criterion is two-sided.
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

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"public_api_result_typed should skip modules without __all__; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_accepts_bare_safe_decorator(*, tmp_path: Path) -> None:
    """A `@safe` (bare, not Call form) decorator passes the check.

    Raises for the same reason as the Call-form case above: a total body would
    be member-1 exempt since livespec v179, and this test would pass without
    the bare-decorator branch ever running.

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
        "    if x < 0:\n"
        "        raise ValueError(x)\n"
        "    return x\n",
        encoding="utf-8",
    )

    _consume(tmp_path=tmp_path, module="foo", name="compute")

    result = _run_check(cwd=tmp_path)

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

    The fixture RAISES for the same reason as the non-Result case above: since
    livespec v179 the rule reaches a public function only when it HAS an
    expected failure mode, so an unannotated `return x` is member-1 exempt and
    the branch under test would never be reached.
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
        "    if x < 0:\n"
        "        raise ValueError(x)\n"
        "    return x\n",
        encoding="utf-8",
    )

    _consume(tmp_path=tmp_path, module="foo", name="compute")

    result = _run_check(cwd=tmp_path)

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

    _consume(tmp_path=tmp_path, module="foo", name="_helper")

    result = _run_check(cwd=tmp_path)

    assert result.returncode == 0, (
        f"public_api_result_typed should ignore private function; "
        f"got returncode={result.returncode}"
    )


def test_public_api_result_typed_rejects_declared_tree_with_no_python(*, tmp_path: Path) -> None:
    """A declared pure_trees path containing no Python files is a misdeclaration."""
    result = _run_check(cwd=tmp_path)

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


def _every_function(*, body: str) -> frozenset[str]:
    """Every top-level function in `body`, as this file's stand-in for v178.

    These are EXEMPTION tests, not criterion tests: each asks what the rule
    does once a function is public. Handing the scan every function keeps that
    subject intact and makes the assertions strictly stronger, since nothing
    can pass merely by falling out of scope. The criterion itself is tested in
    `test_public_api_criterion.py`.
    """
    tree = ast.parse(body)
    return frozenset(
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    )


def _offenders(*, body: str, rel: str = "commands/run.py") -> list[tuple[int, str]]:
    """Run the offender scan over `body` as if it lived at `rel`."""
    from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders

    return _find_offenders(
        source=body,
        rel_path=Path(rel),
        commands_trees=_EXEMPT_TREES,
        public_names=_every_function(body=body),
    )


def _offenders_with_supervisors(
    *, body: str, rel: str, supervisor_entry_files: tuple[Path, ...]
) -> list[tuple[int, str]]:
    """Run the offender scan with a declared `supervisor_entry_files` set."""
    from livespec_dev_tooling.checks.public_api_result_typed import _find_offenders

    return _find_offenders(
        source=body,
        rel_path=Path(rel),
        commands_trees=_EXEMPT_TREES,
        public_names=_every_function(body=body),
        supervisor_entry_files=supervisor_entry_files,
    )


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


def test_public_api_result_typed_treats_a_leading_underscore_as_not_public() -> None:
    """A `_`-prefixed name is NOT public API, even when listed in `__all__`.

    The ratified rule binds "every PUBLIC function's return annotation".
    Python's own convention (PEP 8) makes a leading underscore the marker
    of a non-public name, and this repo relies on that: several modules
    list `_`-prefixed helpers in `__all__` purely so their tests may
    import them. `checks/check_mutation.py` is the clearest case — its
    `__all__` holds SIX `_`-prefixed helpers and does not list `main` at
    all, so there `__all__` is a test-visibility declaration rather than
    a public-API one.

    State the tension precisely rather than pretending it is absent:
    `__all__` IS Python's explicit export declaration, so a name in it is
    public BY DECLARATION on a strict reading. The rule adopted here is
    that the underscore is DECISIVE and wins over `__all__` membership,
    because the alternative reports a private helper as unrailed public
    API — a false positive of exactly the kind an unwired exemption
    would have produced.
    """
    body = (
        "__all__: list[str] = ['_helper']\n\n\n"
        "def _helper(*, x: int) -> bool:\n    return bool(x)\n"
    )

    assert (
        _offenders(body=body, rel="livespec_dev_tooling/checks/thing.py") == []
    ), "a `_`-prefixed name in __all__ is not public API and must not be flagged"


def test_public_api_result_typed_honors_a_declared_supervisor_entry_file() -> None:
    """A file declared in `supervisor_entry_files` gets the supervisor exemption.

    Member 4 of the EXHAUSTIVE exemption set ratified in livespec v177
    (`non-functional-requirements.md` §"ROP composition"). It admits the SAME
    category as the `commands/*.py` members — a supervisor at a deliberate
    side-effect boundary — through a per-file declaration rather than a
    directory glob, because a flat-layout consumer cannot satisfy a location
    scoping at all: its process entry points sit beside its ordinary modules.

    The declaration is STRICTER than the glob it complements. `commands/*.py`
    exempts every present and future file in that directory with nobody
    deciding anything; this names one file, and a repo that has not spoken
    gets nothing — which the companion assertion below pins.
    """
    body = "__all__: list[str] = ['main']\n\n\ndef main() -> int:\n    return 0\n"
    declared = (Path("livespec_dev_tooling/tdd_commit.py"),)

    assert (
        _offenders_with_supervisors(
            body=body, rel="livespec_dev_tooling/tdd_commit.py", supervisor_entry_files=declared
        )
        == []
    ), "a declared supervisor entry file's main() -> int is exempt"

    assert _offenders_with_supervisors(
        body=body, rel="livespec_dev_tooling/other.py", supervisor_entry_files=declared
    ) == [(4, "main")], "an UNDECLARED file gets nothing — silence is not consent"


def test_declared_supervisor_file_does_not_exempt_every_function_in_it() -> None:
    """Member 4 is BOUNDED: it exempts supervisor entry points, not the whole file.

    v177 states this explicitly, because the tempting reading is that
    declaring a file switches the railway off inside it. A helper that is
    neither a `main()`-shaped entry point nor annotated `None` stays subject
    to the rule even in a declared file.
    """
    body = (
        "__all__: list[str] = ['main', 'helper']\n\n\n"
        "def main() -> int:\n    return 0\n\n\n"
        "def helper(*, x: int) -> bool:\n    return bool(x)\n"
    )
    declared = (Path("livespec_dev_tooling/tdd_commit.py"),)

    assert _offenders_with_supervisors(
        body=body, rel="livespec_dev_tooling/tdd_commit.py", supervisor_entry_files=declared
    ) == [(8, "helper")], "the helper is still on the hook; only the supervisor entry point is not"
