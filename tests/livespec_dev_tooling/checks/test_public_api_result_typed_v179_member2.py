"""The check consults the DECLARED half of v179 — `total_absence_returns`.

Member 2's analysis is tested on fixtures in `test_declared_absence_returns.py`;
what this file pins is that the CHECK consults it, at the check's own entry point.
A correct analysis nothing calls would be the manufactured-confidence shape this
whole epic exists to remove, arriving one level up in the wiring rather than in
the rule — and this check's entire history is what that looks like from outside.
Pinning the wire-up BEFORE that failure can occur is the lesson being used rather
than remembered.

**THE CONTROL IS THE LOAD-BEARING TEST, not the exemption.** A wiring bug that
exempted EVERYTHING would satisfy every positive assertion here on its own, and an
empty offender list is precisely what this check looked like for the years it
scanned zero files. So each exemption is asserted beside the identical fixture
WITHOUT the declaration, which must still report.

The check is invoked IN-PROCESS (`monkeypatch.chdir` + `capsys`) per
`check-tests-no-subprocess-spawn`. `git` is still spawned, because the universe is
the git-derived first-party set `resolve_check_universe()` returns.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._declared_absence_returns import declared_absence_names
from livespec_dev_tooling.checks._no_expected_failure_mode import (
    functions_without_expected_failure_mode,
)
from livespec_dev_tooling.checks.public_api_result_typed import main
from livespec_dev_tooling.config import TotalAbsenceReturn

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


_PARSE_TREE = ".claude-plugin/scripts/livespec/parse"
_COMMANDS_TREE = ".claude-plugin/scripts/livespec/commands"

# An `X | None` whose `None` is a legitimate ABSENCE — the shape member 1's clause
# (e) refuses outright and member 2 exists to relieve. It is deliberately TOTAL
# apart from that: no raise, no try, no I/O. Clause (e) alone keeps it in scope, so
# this fixture isolates member 2 rather than accidentally testing member 1.
_ABSENCE_PUBLIC = (
    "from __future__ import annotations\n"
    "\n"
    '__all__: list[str] = ["tag_part"]\n'
    "\n"
    "\n"
    "def tag_part(*, tag: str) -> str | None:\n"
    "    return tag.split('-')[-1] if '-' in tag else None\n"
)
# NOT `X | None`, and it RAISES — so bound 1 must refuse to admit it and member 1
# must not exempt it either. Declaring this is the mis-declaration bound 1 exists
# to catch.
_RAISING_PUBLIC = (
    "from __future__ import annotations\n"
    "\n"
    '__all__: list[str] = ["compute"]\n'
    "\n"
    "\n"
    "def compute(*, x: int) -> int:\n"
    "    if x < 0:\n"
    "        raise ValueError(x)\n"
    "    return x\n"
)
_CONSUMER = (
    "from __future__ import annotations\n"
    "\n"
    "from livespec.parse.foo import {name}\n"
    "\n"
    "__all__: list[str] = []\n"
    "\n"
    "\n"
    "def run() -> None:\n"
    "    _ = {name}({arg})\n"
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


def _write(*, tmp_path: Path, rel_path: str, source: str) -> None:
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    _ = full.write_text(source, encoding="utf-8")


def _declare_absence(*, tmp_path: Path, function: str) -> None:
    """Append a `total_absence_returns` entry naming `function` in the parse fixture."""
    pyproject = tmp_path / "pyproject.toml"
    existing = pyproject.read_text(encoding="utf-8")
    _ = pyproject.write_text(
        f"{existing}total_absence_returns = [\n"
        f'  {{ file = "{_PARSE_TREE}/foo.py", function = "{function}", '
        'reason = "a tag legitimately has no version component" },\n'
        "]\n",
        encoding="utf-8",
    )


def _fixture(*, tmp_path: Path, source: str, name: str, arg: str) -> None:
    _write(tmp_path=tmp_path, rel_path=f"{_PARSE_TREE}/foo.py", source=source)
    _write(
        tmp_path=tmp_path,
        rel_path=f"{_COMMANDS_TREE}/use.py",
        source=_CONSUMER.format(name=name, arg=arg),
    )


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


def test_an_undeclared_absence_return_is_still_reported(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE CONTROL, and it comes first on purpose.

    Without a declaration, a consumed public `X | None` IS an offender: member 1's
    clause (e) refuses the shape outright. If this ever goes green the exemption
    test below proves nothing, because a wiring bug that exempts everything
    satisfies it too.
    """
    _fixture(tmp_path=tmp_path, source=_ABSENCE_PUBLIC, name="tag_part", arg='tag="a-1"')

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "tag_part" in output, (
        f"an UNDECLARED public `X | None` must stay reported — clause (e) refuses the "
        f"shape; exit_code={exit_code} output={output!r}"
    )


def test_a_declared_absence_return_is_outside_the_rule(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The identical fixture, now DECLARED, passes — the check consults member 2."""
    _fixture(tmp_path=tmp_path, source=_ABSENCE_PUBLIC, name="tag_part", arg='tag="a-1"')
    _declare_absence(tmp_path=tmp_path, function="tag_part")

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code == 0, (
        f"a declared legitimate absence is outside the Result-return rule per v179 "
        f"member 2; exit_code={exit_code} output={output!r}"
    )


def test_declaring_a_non_absence_shape_hard_fails_naming_the_entry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """BOUND 1 at the check's entry point — rejected, not quietly ignored.

    The exit code alone is not the whole assertion. A check that silently dropped
    the entry would ALSO leave `compute` reported and exit non-zero, so this pins
    that the REJECTION is surfaced — the difference between a mis-declaration a
    reviewer sees and one that looks like an ordinary offender.
    """
    _fixture(tmp_path=tmp_path, source=_RAISING_PUBLIC, name="compute", arg="x=1")
    _declare_absence(tmp_path=tmp_path, function="compute")

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0, f"a non-`X | None` declaration must hard-fail; output={output!r}"
    assert (
        "compute" in output and "X | None" in output
    ), f"the diagnostic must name the entry AND why bound 1 refused it; output={output!r}"


def test_a_declaration_that_outlived_its_subject_hard_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """BOUND 3 at the check's entry point, ratified as "MUST NOT be a warning".

    This is the shape the sibling key's detector caught twice on its first day: an
    entry authored from a CONSUMER's import statement, naming a function the file
    does not define.
    """
    _fixture(tmp_path=tmp_path, source=_ABSENCE_PUBLIC, name="tag_part", arg='tag="a-1"')
    _declare_absence(tmp_path=tmp_path, function="deleted_long_ago")

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "deleted_long_ago" in output, (
        f"a declaration whose subject is gone must FAIL, naming the entry; "
        f"exit_code={exit_code} output={output!r}"
    )


def test_the_two_v179_members_are_disjoint_by_construction() -> None:
    """Member 1 and member 2 can never both claim a function, and that is structural.

    Member 1's clause (e) refuses every `X | None`; bound 1 admits ONLY `X | None`.
    So the union the check forms cannot let a declaration mask a member-1 result,
    nor a member-1 result launder an invalid declaration. Asserted rather than
    assumed, because the union is where the two scopings meet and an overlap would
    mean one of the two clauses had drifted.
    """
    sources = {Path("pkg/a.py"): _ABSENCE_PUBLIC, Path("pkg/b.py"): _RAISING_PUBLIC}
    member1 = functions_without_expected_failure_mode(sources=sources, io_trees=())
    member2 = declared_absence_names(
        declared=(
            TotalAbsenceReturn(file=Path("pkg/a.py"), function="tag_part", reason="absence"),
        ),
        sources=sources,
    )

    assert member2 == frozenset(
        {(Path("pkg/a.py"), "tag_part")}
    ), f"member 2 must claim the declared `X | None`; got {member2!r}"
    assert not (member1 & member2), (
        f"the two members MUST be disjoint — clause (e) refuses what bound 1 admits; "
        f"overlap={member1 & member2!r}"
    )
