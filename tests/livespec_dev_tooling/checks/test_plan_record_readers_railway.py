"""The plan-record readers' `IOResult` split — `livespec-dev-tooling-qndn.4`.

The reader-level half of the qndn cluster-3 conversion, for the three modules
that reach something: `_plan_ledger` (a `.livespec.jsonc` read, a `.beads/`
export read, two `bd` subprocesses), `_plan_record_dirs` (the `plan/` walk) and
`_plan_record_timeline` (which composes an injected comment reader). The
CALLER-level half — what each armed check DOES with a failed read — stays in
that check's own outside-in test, beside the verdicts it grades.

WHAT EVERY TEST HERE PINS is one split, asserted from BOTH sides, because
either side alone is half the claim: an invocation that COMPLETES and answers
stays on the success track whatever it answers, and only a read that did not
HAPPEN is a failure. Before the conversion those were the same empty list, and
that is not hypothetical in this family — `livespec-dev-tooling-7b6l` is the
same `[]` arriving from a missing `--include-comments`, and it made 8 of the 10
findings from the first armed console run false positives, each a definitive
`plan_close_evidence` verdict about a timeline nothing had read.

Modules are imported INSIDE the test bodies (never at module scope) so an
unimplemented tree fails on a genuine assertion — `assert path.is_file()` —
rather than dying at collection with an import error.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Protocol

import pytest
from returns.io import IOFailure, IOResult
from returns.unsafe import unsafe_perform_io

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKS_DIR = _REPO_ROOT / "livespec_dev_tooling" / "checks"
_TENANT = "livespec-dev-tooling"
_EPIC = f"{_TENANT}-e1"
_OTHER_EPIC = f"{_TENANT}-e2"
_CREDENTIAL_DENIED = "Error 1045 (28000)"


class _SubprocessRun(Protocol):
    """Typed stand-in for `subprocess.run` monkeypatches."""

    def __call__(self, *args: object, **kwargs: object) -> SimpleNamespace:
        """Return the configured completed-process-like object."""
        ...


def _load(*, name: str) -> ModuleType:
    """Import one checks module fresh from its file path."""
    path = _CHECKS_DIR / f"{name}.py"
    assert path.is_file(), f"{path} should exist"
    spec = importlib.util.spec_from_file_location(f"{name}_railway_under_test", str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: a `@dataclass` in a file-loaded module resolves
    # its own `__module__` through `sys.modules` while building the field list,
    # and an unregistered name makes that lookup raise rather than miss.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_subprocess_run(*, result: SimpleNamespace) -> _SubprocessRun:
    """Return a typed `subprocess.run` replacement that never spawns."""

    def _run(*args: object, **kwargs: object) -> SimpleNamespace:
        _ = args
        _ = kwargs
        return result

    return _run


def _write_livespec_config(*, root: Path, prefix: str = _TENANT) -> None:
    """Create a minimal `.livespec.jsonc` carrying the store prefix."""
    body = "\n".join(
        (
            "{",
            '  "implementation": { "plugin": "livespec-orchestrator-beads-fabro" },',
            '  "livespec-orchestrator-beads-fabro": {',
            f'    "connection": {{ "prefix": "{prefix}" }}',
            "  }",
            "}",
            "",
        )
    )
    _ = (root / ".livespec.jsonc").write_text(body, encoding="utf-8")


def _plan_record(*, root: Path, relative: str) -> None:
    """Create a plan-record directory carrying no anchor file."""
    (root / relative).mkdir(parents=True, exist_ok=True)


def _epic(*, item_id: str = _EPIC) -> dict[str, object]:
    """Build one open same-tenant plan epic record."""
    return {"id": item_id, "type": "epic", "status": "open", "metadata": {"plan_slug": "live"}}


def _locked_read_text(self: Path, **kwargs: object) -> str:
    """Stand in for a file that EXISTS and cannot be read.

    A permission bit cannot express "unreadable" to a root-run suite, so the
    `OSError` is raised at the seam that would raise it in the field.
    """
    _ = self
    _ = kwargs
    raise PermissionError("locked")


def _locked_iterdir(self: Path) -> object:
    """Stand in for a directory that EXISTS and cannot be enumerated."""
    _ = self
    raise PermissionError("locked")


def test_store_prefix_separates_an_answer_from_a_config_it_could_not_read(
    *,
    tmp_path: Path,
) -> None:
    """Absent, malformed and present are three distinct outcomes, not one string.

    Every same-tenant verdict downstream rests on this prefix, so a repo whose
    prefix cannot be resolved has no tenant identity at all — answering with a
    guess would grade one tenant's records against another's.
    """
    ledger = _load(name="_plan_ledger")

    absent = ledger.store_prefix(cwd=tmp_path)
    _ = (tmp_path / ".livespec.jsonc").write_text('{"implementation": {}}', encoding="utf-8")
    malformed = ledger.store_prefix(cwd=tmp_path)
    _write_livespec_config(root=tmp_path)
    resolved = ledger.store_prefix(cwd=tmp_path)

    assert unsafe_perform_io(absent.failure()).reason == "config-unreadable"
    assert unsafe_perform_io(malformed.failure()).reason == "config-malformed"
    assert unsafe_perform_io(resolved.unwrap()) == _TENANT


def test_item_reader_names_every_way_the_read_can_fail_to_happen(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Four distinct failures that all used to arrive as an empty record list.

    `bd-failed` is the one that matters most: it is how an absent
    `BEADS_DOLT_PASSWORD` presents (`Error 1045` on stderr), and the caller
    could not tell it from a tenant holding nothing.
    """
    ledger = _load(name="_plan_ledger")
    beads = tmp_path / ".beads"
    beads.mkdir()
    _ = (beads / "issues.jsonl").write_text("not json\n", encoding="utf-8")
    unparseable_export = ledger.bd_items_reader(repo=tmp_path)

    monkeypatch.setattr(Path, "read_text", _locked_read_text)
    unreadable_export = ledger.bd_items_reader(repo=tmp_path)
    monkeypatch.undo()

    def _absent(*args: object, **kwargs: object) -> SimpleNamespace:
        _ = args
        _ = kwargs
        raise FileNotFoundError("no bd on PATH")

    spawned_repo = tmp_path / "other"
    spawned_repo.mkdir()
    monkeypatch.setattr(ledger.subprocess, "run", _absent)
    unavailable = ledger.bd_items_reader(repo=spawned_repo)
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(
            result=SimpleNamespace(returncode=1, stdout="", stderr=_CREDENTIAL_DENIED)
        ),
    )
    denied = ledger.bd_items_reader(repo=spawned_repo)
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(
            result=SimpleNamespace(returncode=0, stdout='{"data": [1,', stderr="")
        ),
    )
    unparseable_output = ledger.bd_items_reader(repo=spawned_repo)

    assert unsafe_perform_io(unparseable_export.failure()).reason == "export-unparseable"
    assert unsafe_perform_io(unreadable_export.failure()).reason == "export-unreadable"
    assert unsafe_perform_io(unavailable.failure()).reason == "bd-unavailable"
    assert unsafe_perform_io(denied.failure()).reason == "bd-failed"
    assert _CREDENTIAL_DENIED in unsafe_perform_io(denied.failure()).detail
    assert unsafe_perform_io(unparseable_output.failure()).reason == "bd-output-unparseable"


def test_comment_reader_separates_an_empty_timeline_from_an_unread_one(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A record that HAS no comments answers `[]`; a `bd` that failed does not answer.

    The two success arms both mean "this record carries no timeline" — a
    payload with no `comments` key, and a payload with no record at all — and
    they are honest answers only because `--include-comments` is passed
    unconditionally. The non-zero exit is the arm that changed track.
    """
    ledger = _load(name="_plan_ledger")
    payload = '{"data":[{"id":"e1","comments":[{"id":"c1","text":"hi"},7]}]}'
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(result=SimpleNamespace(returncode=0, stdout=payload, stderr="")),
    )
    carried = ledger.bd_comments_reader(repo=tmp_path, item_id="e1")
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(
            result=SimpleNamespace(returncode=0, stdout='{"data":[{"id":"e1"}]}', stderr="")
        ),
    )
    keyless = ledger.bd_comments_reader(repo=tmp_path, item_id="e1")
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(result=SimpleNamespace(returncode=0, stdout="", stderr="")),
    )
    recordless = ledger.bd_comments_reader(repo=tmp_path, item_id="e1")
    monkeypatch.setattr(
        ledger.subprocess,
        "run",
        _fake_subprocess_run(
            result=SimpleNamespace(returncode=1, stdout="", stderr=_CREDENTIAL_DENIED)
        ),
    )
    unread = ledger.bd_comments_reader(repo=tmp_path, item_id="e1")

    assert unsafe_perform_io(carried.unwrap()) == [{"id": "c1", "text": "hi"}]
    assert unsafe_perform_io(keyless.unwrap()) == []
    assert unsafe_perform_io(recordless.unwrap()) == []
    assert unsafe_perform_io(unread.failure()).reason == "bd-failed"


def test_descendant_offenders_carries_the_readers_failure_through(*, tmp_path: Path) -> None:
    """An unread ledger is not "no incomplete descendants" — the two were one list.

    The no-closed-anchor arm resolves with NO read at all, so it stays a
    success even when the injected reader would have refused.
    """
    ledger = _load(name="_plan_ledger")
    sentinel = ledger.LedgerReadFailed(reason="bd-failed", detail=f"exit 1: {_CREDENTIAL_DENIED}")

    def _refusing(*, repo: Path) -> IOResult[list[dict[str, object]], object]:
        _ = repo
        return IOFailure(sentinel)

    tenant = ledger.tenant_id_re(tenant_prefix=_TENANT)
    unread = ledger.descendant_offenders(
        statuses=[(tmp_path / "plan/archive/done", _EPIC, "closed")],
        item_reader=_refusing,
        tenant_id_re=tenant,
        repo=tmp_path,
    )
    no_population = ledger.descendant_offenders(
        statuses=[(tmp_path / "plan/live", _EPIC, "open")],
        item_reader=_refusing,
        tenant_id_re=tenant,
        repo=tmp_path,
    )

    assert unsafe_perform_io(unread.failure()) is sentinel
    assert unsafe_perform_io(no_population.unwrap()) == []


def test_a_plan_tree_that_cannot_be_walked_is_not_an_empty_one(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ABSENT `plan/` tree answers with nothing; an unwalkable one fails the scan.

    Both were the same empty list before, and `plan_anchor_present` grades what
    it is handed — so a checkout the scan could not walk read as a conforming
    repo that keeps no plan records.
    """
    dirs = _load(name="_plan_record_dirs")
    ledger = _load(name="_plan_ledger")
    tenant = ledger.tenant_id_re(tenant_prefix=_TENANT)
    _plan_record(root=tmp_path, relative="plan/live")

    no_tree = dirs.plan_directories(plan_dir=tmp_path / "absent", tenant_re=tenant)
    monkeypatch.setattr(Path, "iterdir", _locked_iterdir)
    unwalkable = dirs.plan_directories(plan_dir=tmp_path / "plan", tenant_re=tenant)

    assert unsafe_perform_io(no_tree.unwrap()) == []
    failed = unsafe_perform_io(unwalkable.failure())
    assert failed.reason == "plan-tree-unreadable"
    assert "locked" in failed.detail


def test_one_unread_timeline_fails_the_whole_family(*, tmp_path: Path) -> None:
    """A timeline the reader never obtained takes the family to the failure track.

    Continuing would emit the three verdicts for every OTHER epic and report
    the set as complete, and `plan_close_evidence` — which fires on the ABSENCE
    of a comment — would convict the skipped epic on an absence it never
    established. That is `livespec-dev-tooling-7b6l` exactly.
    """
    timeline = _load(name="_plan_record_timeline")
    ledger = _load(name="_plan_ledger")
    sentinel = ledger.LedgerReadFailed(reason="bd-failed", detail=f"exit 1: {_CREDENTIAL_DENIED}")
    read_ids: list[str] = []

    def _comments(*, repo: Path, item_id: str) -> IOResult[list[dict[str, object]], object]:
        _ = repo
        read_ids.append(item_id)
        return IOFailure(sentinel)

    unread = timeline.timeline_findings(
        epics=[_epic(), _epic(item_id=_OTHER_EPIC)],
        live_slugs=frozenset({"live"}),
        record_slugs=frozenset({"live"}),
        read_comments=_comments,
        repo=tmp_path,
    )

    assert unsafe_perform_io(unread.failure()) is sentinel
    assert read_ids == [_EPIC], "the family stops at the first unread timeline"


def test_a_pre_railway_reader_answering_with_a_bare_list_is_still_read(*, tmp_path: Path) -> None:
    """An injected reader that answers with a plain `list` is lifted, not rejected.

    `timeline_findings` is a SHIPPED seam: every consumer repo injects its own
    comment reader from its own fixtures, and the conversion changed what that
    injected callable must return without a compat path. Every dev-tooling pin
    bump past v1.70.0 then died on `'list' object has no attribute 'unwrap'`
    (`livespec-dev-tooling-fxar2z`), which is a fleet-wide stall rather than a
    consumer bug — the seam owes the older shape an answer.

    The rate WARN is asserted rather than mere survival, because "it did not
    raise" would also hold if the comments had been dropped on the floor; the
    verdict proves the bare list was READ.
    """
    timeline = _load(name="_plan_record_timeline")
    day = "2026-09-10"

    def _comments(*, repo: Path, item_id: str) -> list[dict[str, object]]:
        _ = repo
        _ = item_id
        return [{"text": "note", "created_at": f"{day}T0{hour}:00:00Z"} for hour in range(7)]

    lifted = timeline.timeline_findings(
        epics=[_epic()],
        live_slugs=frozenset(),
        record_slugs=frozenset(),
        read_comments=_comments,
        repo=tmp_path,
    )

    findings = unsafe_perform_io(lifted.unwrap())
    assert [finding.check_id for finding in findings] == ["plan_comment_rate"]
    assert day in findings[0].message
