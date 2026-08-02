"""The check consults v183's condition-3 carrier — `single_meaning_variants`.

The gate's own analysis is tested on fixtures in `test_single_meaning_variants.py`;
what this file pins is that the CHECK consults it, at the check's own entry point.
A correct analysis nothing calls would be the manufactured-confidence shape this
whole epic exists to remove, arriving one level up in the wiring rather than in
the rule — and this check's entire history is what that looks like from outside.

**THE CONTROL IS THE LOAD-BEARING TEST, not the relief.** This key is
RELAXING-ONLY, so a wiring bug that exempted EVERYTHING would satisfy every
positive assertion here on its own — and an empty offender list is precisely what
this check looked like for the years it scanned zero files. So the identical
fixture is asserted WITHOUT the declaration first, and it must still report.

**AND THE NON-VACUITY PROOF IS HERE TOO.** A gate that could only relieve would be
indistinguishable from a blind one, so a fixture that is a condition-1 BOUNDARY is
asserted to stay reported WITH the declaration in place. v183: the carrier "does
NOT reach condition 1".

The check is invoked IN-PROCESS (`monkeypatch.chdir` + `capsys`) per
`check-tests-no-subprocess-spawn`. `git` is still spawned, because the universe is
the git-derived first-party set `resolve_check_universe()` returns.
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

# A closed union rendered at a boundary. `render` is disqualified by member 1
# clause (b), so it is an offender WITHOUT a declaration, which is what makes
# the relief measurable rather than assumed. It calls NO side-effecting
# primitive directly, so condition 1 HOLDS over it.
#
# ⚠️ ITS `try` RECORDS AND CONTINUES, AND THAT IS LOAD-BEARING RATHER THAN
# INCIDENTAL. An earlier draft used `except ValueError: return Bad(...)`, which
# livespec v186 later made a DISCHARGING NARROW `try` — member 1 then exempted
# `render` on its own and the control below went green while proving nothing
# about the declaration. A control convicted by a rule that later relaxes is a
# control with an expiry date nobody wrote down. This body is convicted by
# v186's limb (iii) — the handler appends and keeps looping — which is the one
# shape the correction deliberately refuses.
_UNION_PUBLIC = (
    "from __future__ import annotations\n"
    "\n"
    "from dataclasses import dataclass\n"
    "\n"
    '__all__: list[str] = ["render"]\n'
    "\n"
    "\n"
    "@dataclass(frozen=True, kw_only=True)\n"
    "class Ok:\n"
    "    note: str = ''\n"
    "\n"
    "\n"
    "@dataclass(frozen=True, kw_only=True)\n"
    "class Bad:\n"
    "    message: str\n"
    "\n"
    "\n"
    "Outcome = Ok | Bad\n"
    "\n"
    "\n"
    "def render(*, raw: str) -> Outcome:\n"
    "    bad: list[str] = []\n"
    "    notes: list[str] = []\n"
    "    for part in raw.split(','):\n"
    "        try:\n"
    "            notes.append(str(int(part)))\n"
    "        except ValueError:\n"
    "            bad.append(part)\n"
    "    return Bad(message=','.join(bad)) if bad else Ok(note=','.join(notes))\n"
)
# The SAME union, returned by a function that calls a filesystem primitive
# DIRECTLY. Condition 1 fails over it, so no declaration may relieve it.
#
# ⚠️ IT STILL CONSTRUCTS BOTH VARIANTS. An earlier draft constructed only `Ok`,
# and limb (c) then rejected the whole declaration — so the test passed for the
# wrong reason and proved nothing about condition 1. A negative control must
# break exactly ONE thing.
_BOUNDARY_PUBLIC = _UNION_PUBLIC.replace(
    '__all__: list[str] = ["render"]', '__all__: list[str] = ["reads"]'
).replace(
    "def render(*, raw: str) -> Outcome:\n"
    "    bad: list[str] = []\n"
    "    notes: list[str] = []\n"
    "    for part in raw.split(','):\n"
    "        try:\n"
    "            notes.append(str(int(part)))\n"
    "        except ValueError:\n"
    "            bad.append(part)\n"
    "    return Bad(message=','.join(bad)) if bad else Ok(note=','.join(notes))\n",
    "def reads(*, path) -> Outcome:\n"
    "    text = path.read_text(encoding='utf-8')\n"
    "    return Ok(note=text) if text else Bad(message='empty')\n",
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


def _declare_variants(*, tmp_path: Path, variants: tuple[str, ...]) -> None:
    """Append a `single_meaning_variants` entry per variant, over the fixture union."""
    pyproject = tmp_path / "pyproject.toml"
    existing = pyproject.read_text(encoding="utf-8")
    entries = "".join(
        f'  {{ file = "{_PARSE_TREE}/foo.py", union = "Outcome", variant = "{variant}", '
        f'meaning = "exactly one thing: {variant}" }},\n'
        for variant in variants
    )
    _ = pyproject.write_text(
        f"{existing}single_meaning_variants = [\n{entries}]\n", encoding="utf-8"
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


def test_an_undeclared_union_return_is_still_reported(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE CONTROL, and it comes first on purpose.

    Without a declaration, a consumed public function returning a closed union IS
    an offender. If this ever goes green the relief test below proves nothing,
    because a wiring bug that exempts everything satisfies it too.
    """
    _fixture(tmp_path=tmp_path, source=_UNION_PUBLIC, name="render", arg='raw="1"')

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "render" in output, (
        f"an UNDECLARED union return must stay reported — v183 relieves it only on a "
        f"declaration; exit_code={exit_code} output={output!r}"
    )


def test_a_declared_single_meaning_union_is_outside_the_rule(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The identical fixture, now DECLARED, passes — the check consults the carrier."""
    _fixture(tmp_path=tmp_path, source=_UNION_PUBLIC, name="render", arg='raw="1"')
    _declare_variants(tmp_path=tmp_path, variants=("Ok", "Bad"))

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code == 0, (
        f"a declared single-meaning union satisfies the Result-return rule at a "
        f"rendering boundary per v183; exit_code={exit_code} output={output!r}"
    )


def test_a_condition_1_boundary_is_reported_despite_the_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """NON-VACUITY at the check's entry point — the carrier does NOT reach condition 1.

    The same instrument must be able to REFUSE as well as relieve. A function
    returning the declared union that calls a side-effecting primitive DIRECTLY
    stays convicted, because the ratified text forbids using this clause to avoid
    converting a leaf.
    """
    _fixture(tmp_path=tmp_path, source=_BOUNDARY_PUBLIC, name="reads", arg="path=None")
    _declare_variants(tmp_path=tmp_path, variants=("Ok", "Bad"))

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0 and "reads" in output, (
        f"a condition-1 boundary returning a DECLARED union must stay reported; "
        f"exit_code={exit_code} output={output!r}"
    )


def test_an_incomplete_variant_set_hard_fails_naming_the_entry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """BOUND 3 at the check's entry point, ratified as "MUST NOT be a warning".

    The exit code alone is not the whole assertion. A check that silently dropped
    the entry would ALSO leave `render` reported and exit non-zero, so this pins
    that the REJECTION is surfaced — the difference between a mis-declaration a
    reviewer sees and one that looks like an ordinary offender.
    """
    _fixture(tmp_path=tmp_path, source=_UNION_PUBLIC, name="render", arg='raw="1"')
    _declare_variants(tmp_path=tmp_path, variants=("Ok",))

    exit_code, output = _run_check(cwd=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert exit_code != 0, f"an incomplete variant set must hard-fail; output={output!r}"
    assert "Outcome" in output and "operand set" in output, (
        f"the diagnostic must name the entry AND why bound 3 refused it; " f"output={output!r}"
    )
