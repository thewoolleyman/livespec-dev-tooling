"""Outside-in tests for the heading-coverage debt register's shared vocabulary + generator.

`livespec_dev_tooling.heading_coverage_debt` is the write side of charter D3
of plan `fleet-heading-coverage-convergence`: it owns the register's path, its
key, its row schema, how a `HEAD` copy is read, and the MECHANICAL generation
that produces `tests/heading-coverage-debt.json` from the live
`tests/heading-coverage.json`.

The generation half is exercised against REAL git repositories, because
`first_seen` is evidence read from history (`git log --reverse` over the
registry path, then one blob read per commit) rather than a value an author
declares. A double would prove only that the code calls the functions it
calls.

Driven IN-PROCESS (`monkeypatch.chdir(tmp_path)` + direct calls) exactly as
`tests/livespec_dev_tooling/checks/test_no_todo_registry_staged_scope.py` is,
so no `COVERAGE_PROCESS_START`-instrumented child races the parallel
dispatcher.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "heading_coverage_debt.py"

_TODO_A: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "spec_file": "spec.md",
    "heading": "## Heading A",
    "test": "TODO",
    "reason": "owed integration-tier test",
    "work_item": "livespec-dev-tooling-aaa",
}
_TODO_B: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "spec_file": "spec.md",
    "heading": "## Heading B",
    "test": "TODO",
    "reason": "owed integration-tier test",
    "work_item": "livespec-dev-tooling-bbb",
}
_UNKEYED_TODO: dict[str, object] = {
    "spec_file": "spec.md",
    "heading": "## Heading with no spec_root",
    "test": "TODO",
    "work_item": "livespec-dev-tooling-ccc",
}
_RESOLVED: dict[str, object] = {
    "spec_root": "SPECIFICATION",
    "spec_file": "spec.md",
    "heading": "## Heading C",
    "test": "tests.consumer.test_thing.test_it",
}


def _load_module() -> ModuleType:
    """Import the module fresh from its file path.

    Loaded by path (not `import livespec_dev_tooling.heading_coverage_debt`) so
    the test exercises the on-disk module the Red→Green hook inspects.
    """
    spec = importlib.util.spec_from_file_location(
        "heading_coverage_debt_under_test", str(_MODULE_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def _git(*, cwd: Path, args: list[str], committed_at: str | None = None) -> None:
    # S603/S607: argv is a fixed list (literal git binary + test-controlled
    # args); bare `git` is the canonical invocation per system PATH; no
    # untrusted shell input.
    env = {
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "PATH": "/usr/bin:/bin",
    }
    if committed_at is not None:
        env["GIT_AUTHOR_DATE"] = committed_at
        env["GIT_COMMITTER_DATE"] = committed_at
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )


def _write_registry(*, tmp_path: Path, entries: object) -> None:
    """Write `entries` to the fixture's `tests/heading-coverage.json`."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    _ = (tests_dir / "heading-coverage.json").write_text(
        json.dumps(entries, indent=2) + "\n", encoding="utf-8"
    )


def _commit_registry(*, tmp_path: Path, entries: object, committed_at: str) -> None:
    """Overwrite the registry with `entries` and commit it at `committed_at`."""
    _write_registry(tmp_path=tmp_path, entries=entries)
    _git(cwd=tmp_path, args=["add", "tests/heading-coverage.json"])
    _git(
        cwd=tmp_path,
        args=["commit", "-q", "-m", f"registry at {committed_at}"],
        committed_at=committed_at,
    )


def _seed_repo(*, tmp_path: Path) -> None:
    """A repo whose registry history is: A only, then unreadable, then A + B + resolved.

    The middle commit's registry is a JSON OBJECT rather than an array, which is
    what puts an unparseable historical blob on the walk — the arm that must be
    skipped rather than crash the generator. The first and last commits differ
    so `first_seen` can be asserted per key rather than per file.
    """
    _git(cwd=tmp_path, args=["init", "-q"])
    _git(cwd=tmp_path, args=["config", "user.email", "test@example.com"])
    _git(cwd=tmp_path, args=["config", "user.name", "Test"])
    _commit_registry(
        tmp_path=tmp_path,
        entries=[_TODO_A, _UNKEYED_TODO],
        committed_at="2026-01-02T00:00:00+00:00",
    )
    _commit_registry(tmp_path=tmp_path, entries={}, committed_at="2026-02-03T00:00:00+00:00")
    _commit_registry(
        tmp_path=tmp_path,
        entries=[_TODO_A, _TODO_B, _RESOLVED],
        committed_at="2026-03-04T00:00:00+00:00",
    )


def test_register_key_is_the_ratified_triple() -> None:
    """The key ratified at v064 is `(spec_root, spec_file, heading)`, in that order."""
    assert _MODULE.register_key(row=_TODO_A) == ("SPECIFICATION", "spec.md", "## Heading A")


def test_register_key_refuses_a_row_missing_a_key_field() -> None:
    """An unkeyed row has no identity the ratchet can track on either side."""
    assert _MODULE.register_key(row=_UNKEYED_TODO) is None


def test_register_row_is_complete_requires_owner_and_first_seen() -> None:
    """A register row carries the key three PLUS `work_item` and `first_seen`."""
    complete: dict[str, object] = {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": "## Heading A",
        "work_item": "livespec-dev-tooling-aaa",
        "first_seen": "2026-01-02",
    }
    assert _MODULE.register_row_is_complete(row=complete) is True
    assert _MODULE.register_row_is_complete(row={**complete, "work_item": "   "}) is False
    assert _MODULE.register_row_is_complete(row={**complete, "first_seen": 20260102}) is False


def test_todo_rows_selects_only_the_debt() -> None:
    """Only `test: "TODO"` rows are debt; a resolved row is not tracked."""
    assert _MODULE.todo_rows(rows=[_TODO_A, _RESOLVED]) == [_TODO_A]


def test_load_rows_answers_none_for_absent_unparseable_and_non_array_files(
    *, tmp_path: Path
) -> None:
    """Every unreadable shape yields no rows; a non-dict element is dropped."""
    assert _MODULE.load_rows(path=tmp_path / "missing.json") == []
    unparseable = tmp_path / "unparseable.json"
    _ = unparseable.write_text("{not json", encoding="utf-8")
    assert _MODULE.load_rows(path=unparseable) == []
    non_array = tmp_path / "object.json"
    _ = non_array.write_text("{}", encoding="utf-8")
    assert _MODULE.load_rows(path=non_array) == []
    mixed = tmp_path / "mixed.json"
    _ = mixed.write_text(json.dumps([_TODO_A, "not a row"]), encoding="utf-8")
    assert _MODULE.load_rows(path=mixed) == [_TODO_A]


def test_head_rows_reads_the_committed_copy_and_answers_none_when_incomparable(
    *, tmp_path: Path
) -> None:
    """`HEAD`'s copy is read from git; a blob `HEAD` does not carry answers `None`."""
    _seed_repo(tmp_path=tmp_path)
    rows = _MODULE.head_rows(cwd=tmp_path, path=Path("tests") / "heading-coverage.json")
    assert rows == [_TODO_A, _TODO_B, _RESOLVED]
    assert _MODULE.head_rows(cwd=tmp_path, path=Path("tests") / "no-such-file.json") is None


def test_head_rows_answers_none_when_git_cannot_be_run(*, tmp_path: Path) -> None:
    """An unrunnable git is one arm with the rest: no comparable copy, said once."""
    assert _MODULE.head_rows(cwd=tmp_path / "does-not-exist", path=Path("x.json")) is None


def test_first_seen_dates_are_read_from_the_earliest_carrying_commit(*, tmp_path: Path) -> None:
    """`first_seen` is EVIDENCE: the committer date of the first blob carrying the row.

    Row A survives into the newest commit and must keep the OLDEST date; row B
    appears only in the newest and must carry that one. The unkeyed row and the
    unparseable middle blob are skipped rather than dated or fatal.
    """
    _seed_repo(tmp_path=tmp_path)
    dates = _MODULE.first_seen_dates(cwd=tmp_path)
    assert dates == {
        ("SPECIFICATION", "spec.md", "## Heading A"): "2026-01-02",
        ("SPECIFICATION", "spec.md", "## Heading B"): "2026-03-04",
    }


def test_first_seen_dates_are_empty_where_there_is_no_history(*, tmp_path: Path) -> None:
    """A tree git cannot read places no key; the caller supplies the fallback."""
    assert _MODULE.first_seen_dates(cwd=tmp_path) == {}


def test_generate_register_carries_key_owner_and_git_derived_first_seen(*, tmp_path: Path) -> None:
    """One row per live `TODO`, sorted by key, with the owner verbatim and a real date."""
    _seed_repo(tmp_path=tmp_path)
    generated = _MODULE.generate_register(cwd=tmp_path, today="2026-09-09")
    assert generated == [
        {
            "spec_root": "SPECIFICATION",
            "spec_file": "spec.md",
            "heading": "## Heading A",
            "work_item": "livespec-dev-tooling-aaa",
            "first_seen": "2026-01-02",
        },
        {
            "spec_root": "SPECIFICATION",
            "spec_file": "spec.md",
            "heading": "## Heading B",
            "work_item": "livespec-dev-tooling-bbb",
            "first_seen": "2026-03-04",
        },
    ]


def test_generate_register_falls_back_to_today_and_never_invents_an_owner(
    *, tmp_path: Path
) -> None:
    """A key git cannot place gets `today`; a non-string owner becomes the empty string.

    The empty owner is deliberately NOT a plausible id: it renders the row
    schema-incomplete, which is what makes the ratchet convict it instead of
    banking an unowned debt as legitimate.
    """
    _seed_repo(tmp_path=tmp_path)
    unowned: dict[str, object] = {
        "spec_root": "SPECIFICATION",
        "spec_file": "spec.md",
        "heading": "## Heading D",
        "test": "TODO",
        "work_item": 17,
    }
    _write_registry(tmp_path=tmp_path, entries=[_UNKEYED_TODO, unowned])
    generated = _MODULE.generate_register(cwd=tmp_path, today="2026-09-09")
    assert generated == [
        {
            "spec_root": "SPECIFICATION",
            "spec_file": "spec.md",
            "heading": "## Heading D",
            "work_item": "",
            "first_seen": "2026-09-09",
        }
    ]


def test_render_register_is_stable_and_newline_terminated() -> None:
    """The on-disk bytes are indented JSON with a trailing newline — diffable."""
    rendered = _MODULE.render_register(rows=[{"heading": "## Héading"}])
    assert rendered == '[\n  {\n    "heading": "## Héading"\n  }\n]\n'


def test_main_writes_the_register_and_regenerating_it_changes_nothing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SCENARIO: the register regenerates from the live registry and matches byte-for-byte.

    The second run is the load-bearing half: a generator whose output drifted
    between identical inputs could not be the mechanical baseline the ratchet
    compares against, and every author would carry an unexplained diff.
    """
    _seed_repo(tmp_path=tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _MODULE.main() == 0
    register = tmp_path / "tests" / "heading-coverage-debt.json"
    first = register.read_bytes()
    assert json.loads(first.decode("utf-8"))[0]["heading"] == "## Heading A"
    assert _MODULE.main() == 0
    assert register.read_bytes() == first
