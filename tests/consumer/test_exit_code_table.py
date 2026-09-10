"""Consumer-tier: the `SPECIFICATION/contracts.md` §"Exit-code table" contract.

The table is what a consumer's CI reads: a `just check-<slug>` recipe, a
`run-check` matrix entry, and a commit hook all branch on the integer a shipped
module returns and on nothing else. Two halves, and they fail independently.

**No shipped module may return an undocumented code.** Asserted statically over
every shipped check AND workflow check by reading the integer constants their
`main()` returns and diffing that set against the codes the table itself
declares. Reading the table rather than restating it is deliberate: a row
deleted from the table convicts the module that still returns the code, which is
the direction that would otherwise rot silently. The section's reserved-range
rule — "each check that defines a new code MUST document it in the check's own
module docstring AND in this table" — is asserted on the same set: a code above
the table's highest row must also be named in its own module's docstring.

**The `0`-on-pass / non-zero-on-fail wire actually holds.** Asserted by driving
a shipped check over two consumer fixtures differing only in whether the source
module under `source_trees` carries the violation the check exists to find. The
clean tree must yield exactly `0`; the violating tree must yield a code the
table documents, accompanied by the structured stderr finding §"CLI surface"
requires ("The non-zero exit MUST be accompanied by structured findings emitted
on stderr describing what failed and where"). Holding everything but the
violation fixed is what makes this a proof rather than a coincidence.

The check is invoked IN-PROCESS (`main()` under `monkeypatch.chdir`) per the
`tests_no_subprocess_spawn` discipline. The `git` the fixture builds is real —
the check derives its file universe from the git index, so there is nothing to
run in-process there — and the inherited `GIT_*` hook variables are scrubbed so
the check's own `git` calls resolve to the fixture rather than to the
surrounding repository (this suite runs from a commit hook during the
green-verified leg, where those variables ARE set).
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONTRACTS = _REPO_ROOT / "SPECIFICATION" / "contracts.md"
_PACKAGE_DIR = _REPO_ROOT / "livespec_dev_tooling"
_SHIPPED_NAMESPACES = ("checks", "workflow_checks")

# A table row: `| `4` | check failed (structured findings on stderr) |`.
_TABLE_ROW = re.compile(r"^\|\s*`(?P<code>\d+)`\s*\|", re.MULTILINE)
_EXIT_CODE_SECTION = re.compile(
    r"^## Exit-code table\n(?P<body>.*?)(?=^## )", re.MULTILINE | re.DOTALL
)

# Vars git sets when invoking a hook. Inherited by the check's own `git`
# children unless scrubbed, which would point them at the surrounding repo.
_GIT_HOOK_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

# The exercised check and the rule it enforces: a class whose base is outside
# the direct-parent allowlist.
_EXERCISED_CHECK = "no_inheritance"
_CLEAN_MODULE = "from __future__ import annotations\n\n__all__: list[str] = []\n"
_VIOLATING_MODULE = (
    "from __future__ import annotations\n\n"
    "__all__: list[str] = []\n\n\n"
    "class Base:\n    pass\n\n\n"
    "class Derived(Base):\n    pass\n"
)

_FIXTURE_PYPROJECT = """\
[tool.livespec_dev_tooling]
source_trees = ["src"]
io_trees = []
commands_trees = []
covered_trees = []
supervisor_entry_files = []
dataclasses_tree = { not_applicable = "fixture" }
pure_trees = { not_applicable = "fixture" }
source_tree_prefixes = { not_applicable = "fixture" }
target_dirs = { not_applicable = "fixture" }
neutral_hook_body_path = { not_applicable = "fixture" }
"""


def _documented_codes() -> set[int]:
    """Every exit code the `Exit-code table` section's own table declares."""
    matched = _EXIT_CODE_SECTION.search(_CONTRACTS.read_text(encoding="utf-8"))
    assert matched is not None, 'contracts.md must carry the "## Exit-code table" section'
    codes = {int(code) for code in _TABLE_ROW.findall(matched.group("body"))}
    assert codes, "the exit-code table must declare at least one code"
    return codes


def _shipped_modules() -> dict[str, Path]:
    """Every shipped slug module, keyed `<namespace>.<slug>`."""
    return {
        f"{namespace}.{path.stem}": path
        for namespace in _SHIPPED_NAMESPACES
        for path in sorted((_PACKAGE_DIR / namespace).glob("*.py"))
        if not path.stem.startswith("_") and path.stem != "__init__"
    }


def _returned_codes(*, source: str) -> set[int]:
    """The integer constants the module's top-level `main()` returns."""
    tree = ast.parse(source)
    mains = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    ]
    return {
        node.value.value
        for main in mains
        for node in ast.walk(main)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, int)
        and not isinstance(node.value.value, bool)
    }


def _git(*, cwd: Path, args: list[str]) -> None:
    """Run a fixed git argv in `cwd`, failing the test on a non-zero exit."""
    # S603: a literal `git` plus a fixed argument list, never a shell string.
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, f"git {args} failed: {completed.stderr}"


def _consumer_fixture(*, root: Path, module_source: str) -> Path:
    """A git-tracked consumer tree whose `src/` carries `module_source`."""
    root.mkdir(parents=True, exist_ok=True)
    _ = root.joinpath("pyproject.toml").write_text(_FIXTURE_PYPROJECT, encoding="utf-8")
    source_dir = root / "src"
    source_dir.mkdir()
    _ = source_dir.joinpath("mod.py").write_text(module_source, encoding="utf-8")
    _git(cwd=root, args=["init", "--quiet", "."])
    _git(cwd=root, args=["add", "--all"])
    return root


def test_no_shipped_module_returns_an_exit_code_the_table_does_not_document() -> None:
    """Every returned code is a documented one, and a reserved code is documented twice."""
    documented = _documented_codes()
    modules = _shipped_modules()
    assert modules, "the library must ship at least one slug module"

    returned = {
        name: _returned_codes(source=path.read_text(encoding="utf-8"))
        for name, path in modules.items()
    }
    undocumented = {
        name: sorted(codes - documented) for name, codes in returned.items() if codes - documented
    }
    assert not undocumented, (
        f"a consumer's CI branches on the integer alone, so a code no row of "
        f'contracts.md §"Exit-code table" declares is an undocumented wire; '
        f"undocumented={undocumented} documented={sorted(documented)}"
    )

    reserved = max(documented)
    undeclared_in_docstring = {
        name: sorted(code for code in codes if code > reserved)
        for name, codes in returned.items()
        if any(
            code > reserved
            and str(code)
            not in (ast.get_docstring(ast.parse(modules[name].read_text(encoding="utf-8"))) or "")
            for code in codes
        )
    }
    assert not undeclared_in_docstring, (
        f"a check defining a code above `{reserved}` MUST document it in its own module "
        f"docstring as well as in the table; undocumented={undeclared_in_docstring}"
    )


def test_a_shipped_check_exits_zero_when_clean_and_a_documented_code_when_violated(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The pass/fail wire holds, and the failure carries structured stderr findings."""
    for name in _GIT_HOOK_VARS:
        monkeypatch.delenv(name, raising=False)
    check = importlib.import_module(f"livespec_dev_tooling.checks.{_EXERCISED_CHECK}")
    documented = _documented_codes()

    monkeypatch.chdir(_consumer_fixture(root=tmp_path / "clean", module_source=_CLEAN_MODULE))
    clean = check.main()
    _ = capsys.readouterr()

    monkeypatch.chdir(
        _consumer_fixture(root=tmp_path / "violating", module_source=_VIOLATING_MODULE)
    )
    violated = check.main()
    findings = [
        json.loads(line) for line in capsys.readouterr().err.splitlines() if line.startswith("{")
    ]

    assert clean == 0, f"a clean consumer tree must exit 0; got {clean}"
    assert violated in documented - {0}, (
        f"a violation must exit a documented non-zero code; got {violated} "
        f"documented={sorted(documented)}"
    )
    located = [
        finding
        for finding in findings
        if finding.get("file") == "src/mod.py" and finding.get("line")
    ]
    assert located, (
        f"the non-zero exit MUST be accompanied by structured findings on stderr "
        f"describing what failed and WHERE; got {findings}"
    )
