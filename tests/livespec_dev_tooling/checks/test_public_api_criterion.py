"""Outside-in test for the v178 public-API criterion in `public_api_result_typed`.

`livespec` v178 (`non-functional-requirements.md` §"ROP composition") replaced
`__all__` membership with CONSUMED ACROSS A BOUNDARY as the definition of public
API for the Result-return rule. This file pins the criterion's OBSERVABLE
behavior at the check's own entry point, in both directions:

- the RELAXING half — a name in `__all__` that nothing consumes is no longer
  reported;
- the TIGHTENING half — a name `__all__` does NOT list but something consumes
  IS reported, so deleting one line is not an escape;
- the DECLARED half — `cross_repo_public_api` adds the names only a sibling
  reaches, and a declaration that no longer resolves is a hard failure.

The declared half's staleness detector is the part with no other guard: a
declaration nobody re-verifies is the defect class this rule set exists to
remove, so SPECIFICATION v036 requires the check to fail on an entry whose
subject is gone rather than carry it forward.

The check is invoked IN-PROCESS (`monkeypatch.chdir` + `capsys`) rather than
through a Python subprocess, per `check-tests-no-subprocess-spawn`. `git` is
still spawned, because the universe these tests exercise is the git-derived
first-party set the check now resolves through `resolve_check_universe()`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks.public_api_result_typed import main

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


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


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def _declare_cross_repo(*, tmp_path: Path, entries: str) -> None:
    """Append a `cross_repo_public_api` array to the fixture's layout block."""
    pyproject = tmp_path / "pyproject.toml"
    existing = pyproject.read_text(encoding="utf-8")
    _ = pyproject.write_text(f"{existing}cross_repo_public_api = [\n{entries}]\n", encoding="utf-8")


def _run_check(
    *, cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    """`git init` + stage the fixture, then run the check in-process from `cwd`."""
    _git(cwd=cwd, args=["init", "-q"])
    _git(cwd=cwd, args=["add", "-A"])
    monkeypatch.chdir(cwd)
    exit_code = main()
    captured = capsys.readouterr()
    return exit_code, captured.out + captured.err


_BARE_INT_PUBLIC = (
    "from __future__ import annotations\n"
    "\n"
    '__all__: list[str] = ["compute"]\n'
    "\n"
    "\n"
    "def compute(*, x: int) -> int:\n"
    "    return x\n"
)
_BARE_INT_UNDECLARED = (
    "from __future__ import annotations\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def compute(*, x: int) -> int:\n"
    "    return x\n"
)
# The consumer imports ABSOLUTELY (`livespec.parse.foo`), which is how a
# LAYERED consumer actually reaches a sibling module: its package root is
# `.claude-plugin/scripts/`, not the repo root. A repo-root-relative reading
# of module identity resolves nothing here, and resolving nothing is the
# RELAXING direction — the dangerous one for this check.
_PRODUCT_CONSUMER = (
    "from __future__ import annotations\n"
    "\n"
    "from livespec.parse.foo import compute\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def run() -> None:\n"
    "    _ = compute(x=1)\n"
)
_DECLARED_REASON = 'reason = "product import: a sibling hook calls it" },\n'


def test_a_consumed_public_function_without_a_result_return_is_rejected(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A product import across a module boundary makes the name public — and reportable."""
    _write(tmp_path=tmp_path, rel_path=f"{_PARSE_TREE}/foo.py", source=_BARE_INT_PUBLIC)
    _write(tmp_path=tmp_path, rel_path=f"{_COMMANDS_TREE}/use.py", source=_PRODUCT_CONSUMER)

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "compute" in output, (
        f"a consumed non-Result public function must be reported by name; "
        f"exit_code={exit_code} output={output!r}"
    )


def test_a_declared_but_unconsumed_function_is_no_longer_public(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`__all__` membership alone no longer makes a name public — the v178 relaxation.

    This is the half that shrinks enforcement scope, and it is a real reduction
    rather than a reclassification: it removes 25 of this repo's 31 reported
    offenders.
    """
    _write(tmp_path=tmp_path, rel_path=f"{_PARSE_TREE}/foo.py", source=_BARE_INT_PUBLIC)

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code == 0, (
        f"an unconsumed `__all__` member is a TEST-VISIBILITY EXPORT, not public API; "
        f"exit_code={exit_code} output={output!r}"
    )


def test_a_consumed_function_absent_from_all_is_still_public(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deleting the `__all__` line is NOT an escape — the anti-gaming half of v178.

    The criterion is `__all__`-INDEPENDENT in the tightening direction, stated
    as a requirement because the relaxing half is otherwise silenced by removing
    one line.
    """
    _write(tmp_path=tmp_path, rel_path=f"{_PARSE_TREE}/foo.py", source=_BARE_INT_UNDECLARED)
    _write(tmp_path=tmp_path, rel_path=f"{_COMMANDS_TREE}/use.py", source=_PRODUCT_CONSUMER)

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "compute" in output, (
        f"a consumed function must be public whether or not `__all__` lists it; "
        f"exit_code={exit_code} output={output!r}"
    )


def test_a_cross_repo_declaration_makes_an_unconsumed_function_public(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A declared entry adds a name no repo-local form reaches.

    This is the `parse_manifest` shape: zero importers in the declaring repo,
    one in a sibling's hook. A repo-local oracle alone calls it not-public —
    the exact reading whose conversion turned a sibling's master RED.
    """
    _write(tmp_path=tmp_path, rel_path=f"{_PARSE_TREE}/foo.py", source=_BARE_INT_UNDECLARED)
    _declare_cross_repo(
        tmp_path=tmp_path,
        entries=f'  {{ file = "{_PARSE_TREE}/foo.py", function = "compute", {_DECLARED_REASON}',
    )

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "compute" in output, (
        f"a declared cross-repo-consumed function must be in scope; "
        f"exit_code={exit_code} output={output!r}"
    )


def test_a_declaration_naming_a_missing_function_is_a_hard_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A declaration MUST NOT outlive its subject — SPECIFICATION v036 bound 3."""
    _write(tmp_path=tmp_path, rel_path=f"{_PARSE_TREE}/foo.py", source=_BARE_INT_PUBLIC)
    _declare_cross_repo(
        tmp_path=tmp_path,
        entries=(
            f'  {{ file = "{_PARSE_TREE}/foo.py", function = "renamed_away", {_DECLARED_REASON}'
        ),
    )

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "renamed_away" in output, (
        f"a stale declaration must fail loudly and name the entry; "
        f"exit_code={exit_code} output={output!r}"
    )


def test_a_declaration_naming_a_missing_file_is_a_hard_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An entry pointing at a file outside the first-party universe fails the same way."""
    _write(tmp_path=tmp_path, rel_path=f"{_PARSE_TREE}/foo.py", source=_BARE_INT_PUBLIC)
    _declare_cross_repo(
        tmp_path=tmp_path,
        entries=f'  {{ file = "{_PARSE_TREE}/deleted.py", function = "compute", {_DECLARED_REASON}',
    )

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "deleted.py" in output, (
        f"a declaration naming an absent file must fail loudly; "
        f"exit_code={exit_code} output={output!r}"
    )
