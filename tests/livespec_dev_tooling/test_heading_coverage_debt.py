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

The two `main()` tests at the foot of this file carry an explicit
`pytest.mark.integration` — the `scenarios.md` heading "the heading-coverage
debt register regenerates from the live registry and matches byte-for-byte"
maps to the first of them, and `heading_coverage` direction 4 resolves a
scenario's tier either from an allowlisted node-id prefix or from that static
marker. The marker is FUNCTION-level rather than module-level on purpose: this
file is genuinely mixed-tier, and the vocabulary tests above it
(`register_key`, `todo_rows`, `render_register`) are pure unit-tier, so a
module-level `pytestmark` would mislabel them. The marker selects nothing —
no recipe or workflow passes `-m`.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

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

    Registered in `sys.modules` under its synthetic name BEFORE execution, for
    the reason `test_heading_coverage_debt_register.py` already records: on
    Python 3.10 `@dataclass` resolves `KW_ONLY` by looking the defining module
    up there, and a path-loaded module absent from `sys.modules` makes that
    lookup raise on the class body rather than on anything this test asserts.
    """
    spec = importlib.util.spec_from_file_location(
        "heading_coverage_debt_under_test", str(_MODULE_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
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


def test_load_rows_answers_an_absent_file_with_no_rows(*, tmp_path: Path) -> None:
    """ABSENCE STAYS AN ANSWER: a consumer that has not adopted the register has no file.

    The load-bearing contrast is with
    `test_load_rows_fails_for_a_present_file_it_cannot_read` below: both used to
    return `[]`, and they are on OPPOSITE tracks now.
    """
    loaded = _MODULE.load_rows(path=tmp_path / "missing.json")

    assert isinstance(loaded, IOSuccess)
    assert unsafe_perform_io(loaded.unwrap()) == []


def test_load_rows_reads_the_rows_and_drops_a_non_dict_element(*, tmp_path: Path) -> None:
    """A real array is a success; an element that is not a row is skipped, not fatal."""
    mixed = tmp_path / "mixed.json"
    _ = mixed.write_text(json.dumps([_TODO_A, "not a row"]), encoding="utf-8")

    loaded = _MODULE.load_rows(path=mixed)

    assert isinstance(loaded, IOSuccess)
    assert unsafe_perform_io(loaded.unwrap()) == [_TODO_A]


def test_load_rows_fails_for_a_present_file_that_is_not_an_array(*, tmp_path: Path) -> None:
    """Unparseable text and non-array JSON are one meaning — and it is NOT "no rows".

    Answering `[]` here spent an unreadable registry as "there is no debt",
    which is the vacuous pass the ratchet downstream cannot detect.
    """
    unparseable = tmp_path / "unparseable.json"
    _ = unparseable.write_text("{not json", encoding="utf-8")
    non_array = tmp_path / "object.json"
    _ = non_array.write_text("{}", encoding="utf-8")

    for path in (unparseable, non_array):
        loaded = _MODULE.load_rows(path=path)
        assert isinstance(loaded, IOFailure), path
        unreadable = unsafe_perform_io(loaded.failure())
        assert unreadable.reason == "rows-file-not-an-array"
        assert unreadable.path == path.as_posix()


def test_load_rows_fails_for_a_present_file_it_cannot_read(*, tmp_path: Path) -> None:
    """A DIRECTORY where the register belongs is a non-read, and now says so.

    `chmod 000` proves nothing — this suite runs as root — so unreadability is
    spelled as a directory where a file is expected. The resulting
    `IsADirectoryError` is an `OSError` that is NOT a `FileNotFoundError`,
    which matters precisely because absence is the ANSWER arm above. The old
    `is_file()` pre-check returned `[]` for exactly this tree.
    """
    directory = tmp_path / "register-shaped-directory.json"
    directory.mkdir()

    loaded = _MODULE.load_rows(path=directory)

    assert isinstance(loaded, IOFailure)
    unreadable = unsafe_perform_io(loaded.failure())
    assert unreadable.reason == "rows-file-unreadable"
    assert unreadable.detail


def test_head_rows_reads_the_committed_copy(*, tmp_path: Path) -> None:
    """`HEAD`'s copy is read from git and comes back on the success track."""
    _seed_repo(tmp_path=tmp_path)

    rows = _MODULE.head_rows(cwd=tmp_path, path=Path("tests") / "heading-coverage.json")

    assert isinstance(rows, IOSuccess)
    assert unsafe_perform_io(rows.unwrap()) == [_TODO_A, _TODO_B, _RESOLVED]


def test_head_rows_fails_when_head_carries_no_blob(*, tmp_path: Path) -> None:
    """A path `HEAD` does not carry is NOT "empty at HEAD" — no comparison is possible."""
    _seed_repo(tmp_path=tmp_path)

    rows = _MODULE.head_rows(cwd=tmp_path, path=Path("tests") / "no-such-file.json")

    assert isinstance(rows, IOFailure)
    incomparable = unsafe_perform_io(rows.failure())
    assert incomparable.reason == "head-copy-absent"
    assert incomparable.revision == "HEAD:tests/no-such-file.json"


def test_head_rows_fails_when_git_cannot_be_run(*, tmp_path: Path) -> None:
    """An unrunnable git rides with the absent blob: no comparable copy, said once."""
    rows = _MODULE.head_rows(cwd=tmp_path / "does-not-exist", path=Path("x.json"))

    assert isinstance(rows, IOFailure)
    assert unsafe_perform_io(rows.failure()).reason == "head-copy-absent"


def test_head_rows_fails_distinctly_when_the_committed_blob_is_not_an_array(
    *, tmp_path: Path
) -> None:
    """A committed blob that IS there and is not a registry is its own defect.

    Split from `head-copy-absent` because an operator acts on them differently:
    an absent blob is ordinary (adoption, a fresh clone), while a committed
    non-array is something that was actually written wrong.
    """
    _seed_repo(tmp_path=tmp_path)
    _commit_registry(tmp_path=tmp_path, entries={}, committed_at="2026-05-06T00:00:00+00:00")

    rows = _MODULE.head_rows(cwd=tmp_path, path=Path("tests") / "heading-coverage.json")

    assert isinstance(rows, IOFailure)
    assert unsafe_perform_io(rows.failure()).reason == "head-copy-not-an-array"


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
    assert isinstance(generated, IOSuccess)
    assert unsafe_perform_io(generated.unwrap()) == [
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
    assert isinstance(generated, IOSuccess)
    assert unsafe_perform_io(generated.unwrap()) == [
        {
            "spec_root": "SPECIFICATION",
            "spec_file": "spec.md",
            "heading": "## Heading D",
            "work_item": "",
            "first_seen": "2026-09-09",
        }
    ]


def test_generate_register_propagates_an_unreadable_registry(*, tmp_path: Path) -> None:
    """A registry that will not parse must NOT generate an empty register.

    This is the failure the conversion exists for: the old `[]` answer made the
    generator produce a register with no rows, and `main()` then wrote it over
    the real one — the whole debt banked as resolved by one unparseable file.
    """
    _seed_repo(tmp_path=tmp_path)
    _write_registry(tmp_path=tmp_path, entries={"not": "an array"})

    generated = _MODULE.generate_register(cwd=tmp_path, today="2026-09-09")

    assert isinstance(generated, IOFailure)
    assert unsafe_perform_io(generated.failure()).reason == "rows-file-not-an-array"


def test_render_register_is_stable_and_newline_terminated() -> None:
    """The on-disk bytes are indented JSON with a trailing newline — diffable."""
    rendered = _MODULE.render_register(rows=[{"heading": "## Héading"}])
    assert rendered == '[\n  {\n    "heading": "## Héading"\n  }\n]\n'


@pytest.mark.integration
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


@pytest.mark.integration
def test_main_refuses_to_overwrite_the_register_from_an_unreadable_registry(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """SCENARIO: the generator declines, LOUDLY, and leaves the real register alone.

    The bytes on disk are the assertion that matters. Before the conversion this
    tree produced `[]` and wrote it, which reads to the ratchet as a register
    that legitimately shrank to nothing — a silent, total exemption authored by
    a file nobody could parse.
    """
    _seed_repo(tmp_path=tmp_path)
    monkeypatch.chdir(tmp_path)
    assert _MODULE.main() == 0
    register = tmp_path / "tests" / "heading-coverage-debt.json"
    before = register.read_bytes()
    _write_registry(tmp_path=tmp_path, entries={"not": "an array"})

    assert _MODULE.main() == 1

    assert register.read_bytes() == before
    combined = capsys.readouterr()
    assert "rows-file-not-an-array" in combined.out + combined.err
