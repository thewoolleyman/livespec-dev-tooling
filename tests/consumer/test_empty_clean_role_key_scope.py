"""Consumer-tier: `SPECIFICATION/scenarios.md` §"an empty clean role key makes its consuming check stricter, not blinder".

    Given a consumer declares `io_trees` as a bare `[]`
    When the catch-position and domain-raise checks run
    Then they MUST inspect the consumer's full first-party universe
    And the number of files inspected MUST be non-zero
    And no file MUST be wholesale exempt by virtue of that empty declaration

The two checks the scenario names are the shipped `no_except_outside_io`
(catch POSITION) and `no_raise_outside_io` (domain RAISE). Both are driven the
way a consumer drives them — over a real fixture repository, in-process, with
the exit code and the structlog stderr as the only observables.

THE CONTROL IS THE POINT. "Stricter, not blinder" is a COMPARISON, and a test
that only ran the empty arm would pass just as happily against a check that
inspected everything unconditionally and honoured no exemption at all. So each
assertion runs BOTH arms over the byte-identical tree — `io_trees = []` and
`io_trees = ["pkg/io"]` — and asserts the empty arm inspects strictly MORE and
convicts a file the populated arm exempts. Neither number is derived from the
same source as the other: the expected universe comes from the fixture's own
tracked `.py` files, and the inspected counts come from each check's own
`files_inspected` field.

The fixture is a real `git init` + `git add -A`, because both checks derive
their universe from the git INDEX (deliberately NOT from `source_trees`, whose
`[]` once meant "scan nothing" while the declaration read as conformance). An
untracked fixture is invisible to them and would pass vacuously.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

from livespec_dev_tooling.checks import no_except_outside_io, no_raise_outside_io
from tests.consumer.role_key_fixture import records_from

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_PROMOTE_ENV_VAR = "LIVESPEC_FAIL_IF_DOMAIN_ERROR_RAISES_EXIST"
_IO_TREE = "pkg/io"
# The file the populated arm exempts wholesale and the empty arm must not: it
# lives under the io tree and both raises a domain error and catches broadly.
_UNDER_THE_IO_TREE = f"{_IO_TREE}/gateway.py"
# The file NO declaration exempts, so it convicts under both arms — the control
# that keeps "the empty arm convicts more" from being satisfiable by a check
# that simply stopped working in the populated arm.
_ALWAYS_INSPECTED = "pkg/pure/compute.py"

_HEADER = "from __future__ import annotations\n\n__all__: list[str] = []\n\n\n"
# `WidgetError` is the consumer's OWN domain error: the name set is derived from
# the classes the repo defines, so a fixture that raises one must also define it.
_MODULES: dict[str, str] = {
    "pkg/__init__.py": "",
    "pkg/errors.py": 'class WidgetError(Exception):\n    """The consumer\'s domain error."""\n',
    _ALWAYS_INSPECTED: 'def compute() -> None:\n    raise WidgetError("pure layer")\n',
    _UNDER_THE_IO_TREE: (
        "def fetch() -> None:\n"
        '    raise WidgetError("io layer")\n'
        "\n\n"
        "def guarded() -> None:\n"
        "    try:\n"
        "        fetch()\n"
        "    except Exception:\n"
        "        return\n"
    ),
}


class _Run(NamedTuple):
    """One check's consumer-observable result."""

    returncode: int
    records: list[dict[str, object]]


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


def _fixture(*, root: Path, io_trees: str) -> Path:
    """A tracked consumer repository whose ONLY variable is the `io_trees` value."""
    root.mkdir(parents=True, exist_ok=True)
    _ = root.joinpath("pyproject.toml").write_text(
        '[project]\nname = "consumer"\nversion = "0.0.0"\n\n'
        "[tool.livespec_dev_tooling]\n"
        'source_trees = ["pkg"]\n'
        f"io_trees = {io_trees}\n"
        "commands_trees = []\n"
        "covered_trees = []\n"
        "supervisor_entry_files = []\n"
        'pure_trees = { not_applicable = "fixture" }\n'
        'target_dirs = { not_applicable = "fixture" }\n'
        'source_tree_prefixes = { not_applicable = "fixture" }\n'
        'dataclasses_tree = { not_applicable = "fixture" }\n'
        'neutral_hook_body_path = { not_applicable = "fixture" }\n',
        encoding="utf-8",
    )
    for rel, body in _MODULES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(_HEADER + body if body else _HEADER, encoding="utf-8")
    _git(cwd=root, args=["init", "-q"])
    _git(cwd=root, args=["add", "-A"])
    return root


def _run(
    *,
    check: str,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> _Run:
    """Drive one shipped check over `root` the way a consumer does."""
    monkeypatch.setenv(_PROMOTE_ENV_VAR, "true")
    monkeypatch.chdir(root)
    code = no_raise_outside_io.main() if check == "raise" else no_except_outside_io.main()
    captured = capsys.readouterr()
    return _Run(returncode=code, records=records_from(captured=captured.out + captured.err))


def _inspected(*, run: _Run) -> int:
    """The `files_inspected` count the check reports on every run."""
    counts = [record["files_inspected"] for record in run.records if "files_inspected" in record]
    assert len(counts) == 1, (
        f"each check reports its inspected count exactly once, on every run — an "
        f"inspected count of zero otherwise reads exactly like a clean pass; got {counts!r}"
    )
    count = counts[0]
    assert isinstance(count, int)
    return count


def _convicted_files(*, run: _Run) -> set[str]:
    """The files the check reported an offense against, by relative path.

    Keyed on records carrying a `line`: those are the per-offense findings.
    A backstop-probe record names a file without a line and is not an offense
    against that file's contents.
    """
    return {
        str(record["file"])
        for record in run.records
        if "line" in record and "file" in record and record.get("level") in ("error", "warning")
    }


@pytest.mark.parametrize("check", ["raise", "except"])
def test_an_empty_io_trees_inspects_the_whole_first_party_universe(
    *,
    check: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Both named checks inspect every first-party file, and strictly more than the control."""
    empty = _run(
        check=check,
        root=_fixture(root=tmp_path / "empty", io_trees="[]"),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    populated = _run(
        check=check,
        root=_fixture(root=tmp_path / "populated", io_trees=f'["{_IO_TREE}"]'),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    universe = len(_MODULES)
    assert _inspected(run=empty) == universe, (
        f"with `io_trees` declared empty the check MUST inspect the consumer's FULL "
        f"first-party universe — every one of the fixture's {universe} tracked modules — "
        f"because an empty CLEAN key removes exemptions rather than files; "
        f"got {_inspected(run=empty)}"
    )
    assert _inspected(run=empty) > 0, (
        "the number of files inspected MUST be non-zero: a check inspecting nothing "
        "reports exactly like a clean pass, which is the scope dodge this clause forbids"
    )
    assert _inspected(run=empty) > _inspected(run=populated), (
        f"the empty declaration must make the check STRICTER than a populated one, not "
        f"blinder. Equal counts would mean the exemption never worked at all, so this "
        f"comparison is what keeps the assertion above from passing vacuously; "
        f"empty={_inspected(run=empty)} populated={_inspected(run=populated)}"
    )


def test_no_file_is_wholesale_exempt_by_virtue_of_the_empty_declaration(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The file the populated arm exempts is convicted by the empty one, on its contents."""
    empty = _run(
        check="raise",
        root=_fixture(root=tmp_path / "empty", io_trees="[]"),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )
    populated = _run(
        check="raise",
        root=_fixture(root=tmp_path / "populated", io_trees=f'["{_IO_TREE}"]'),
        monkeypatch=monkeypatch,
        capsys=capsys,
    )

    assert _ALWAYS_INSPECTED in _convicted_files(run=populated), (
        f"the control file must convict under BOTH arms, or 'the empty arm convicts more' "
        f"could be satisfied by a check that simply stopped working; "
        f"got {_convicted_files(run=populated)!r}"
    )
    assert _UNDER_THE_IO_TREE not in _convicted_files(run=populated), (
        f"a POPULATED `io_trees` is what grants the wholesale exemption, so the control "
        f"arm must exercise it; got {_convicted_files(run=populated)!r}"
    )
    assert _UNDER_THE_IO_TREE in _convicted_files(run=empty), (
        f"no file MUST be wholesale exempt by virtue of the empty declaration — reading "
        f"`io_trees = []` as 'exempt everything' is the inversion that silently disarmed "
        f"this gate across the fleet; got {_convicted_files(run=empty)!r}"
    )
    assert _convicted_files(run=empty) > _convicted_files(run=populated), (
        f"the empty declaration's conviction set must be a STRICT SUPERSET of the "
        f"populated one's — stricter, never merely different, and never smaller; "
        f"empty={_convicted_files(run=empty)!r} populated={_convicted_files(run=populated)!r}"
    )
    assert empty.returncode != 0 and populated.returncode != 0, (
        f"both arms carry a real offense, so both must fail under the promotion lever: a "
        f"passing arm would mean the comparison above compared a working check with a "
        f"broken one; empty={empty.returncode} populated={populated.returncode}"
    )
