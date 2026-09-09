"""Outside-in tests for the role-key discriminated union — Phase 1, the ACCEPTING loader.

`livespec-dev-tooling-8o8e.1`: a role key's `[]` / `""` spelling carries TWO
incompatible meanings — "the concept does not apply to this repo" and "the
concept applies and is switched off" — and the shared gate reads either as a
sanctioned opt-out. Measured, that silently disarmed `check-public-api-result-typed`
in all nine fleet repos, `check-claude-md-coverage` in five, and the commit-time
TDD pairing gate in three.

Phase 1 teaches the loader FOUR blessed declared-absent spellings, each carrying
its own reason in the PARSED VALUE rather than in a comment no checker can read:

    { not_applicable         = "<reason>" }
    { superseded_by          = "<reason>" }
    { unarmed_until          = "<ledger-id>" }
    { convention_not_adopted = "<reason>" }

Phase 1 REJECTS NOTHING that a repo declares today. A bare `[]` / `""` still
parses and still behaves exactly as today (scan nothing, exit 0), but becomes a
DISTINCT type that announces itself at WARN — so the previously-invisible state is
greppable and countable before any repo migrates. The rejecting loader is Phase 4,
and lands only once all eight Python-bearing repos have migrated.

Each behavioral test drives a real check IN-PROCESS via its `main()` and asserts on
the structlog records it emits, so the assertion is about what a consumer actually
does with the parsed value rather than about the parse in isolation. In-process
rather than subprocess deliberately: `check-tests-no-subprocess-spawn` gates
gratuitous spawns, and nothing here needs a real process boundary.

FIXTURE HAZARD, DELIBERATELY DEFEATED: `tests/livespec_dev_tooling/checks/conftest.py`
overrides `tmp_path` to seed a full legacy `[tool.livespec_dev_tooling]` block —
including a POPULATED `target_dirs`. A test in this directory that merely creates
files inherits that seeded config and proves nothing about its own declaration.
Every test below OVERWRITES `pyproject.toml` outright. The legacy-empty test is
self-guarding on this point: its WARN can only fire when `target_dirs` parses as
the empty spelling, which is reachable only from the block written here — a leaked
fixture value (three populated dirs) would produce no WARN and fail the test.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest
import structlog

from livespec_dev_tooling.checks import (
    _role_key_gate,
    claude_md_coverage,
    public_api_result_typed,
)
from livespec_dev_tooling.checks._work_item_liveness import LedgerUnreachable
from livespec_dev_tooling.config import Config, ConfigParseError, load_config

_VENDOR_DIR = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

# The structured field every declared-absent announcement carries, naming the
# variant the consumer declared.
_SPELLING_FIELD = "role_key_spelling"
# The payload every `unarmed_until` case below declares. Two fleet repos really
# do cite this id on `pure_trees`, which is what made the variant worth
# distinguishing — but every status it resolves to here is SYNTHETIC, supplied by
# an injected store rather than read from the live tenant.
_LEDGER_ID = "livespec-mutreal.1"

__all__: list[str] = []


def _write_config(*, tmp_path: Path, body: str) -> None:
    """Overwrite the fixture-seeded config with exactly the block under test."""
    _ = tmp_path.joinpath("pyproject.toml").write_text(
        f'[project]\nname = "consumer"\nversion = "0.0.0"\n\n'
        f"[tool.livespec_dev_tooling]\n{body}",
        encoding="utf-8",
    )


def _unarmed_record(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    snapshot: dict[str, str] | None,
) -> dict[str, object]:
    """Drive a real check over an `unarmed_until` declaration and return its announcement.

    `snapshot` is the work-item store the shared resolver sees, injected by
    replacing `_role_key_gate`'s module-global reader — the seam the gate looks
    up at CALL time. Nothing here contacts a tracker, opens a socket, or spawns
    a process, and the fixture is SYNTHETIC in both directions: the control's
    validity must not depend on some production repository staying broken.

    The check is driven end-to-end rather than the announcer called directly,
    so what is asserted is what a consumer actually emits.
    """

    answer: IOResult[dict[str, str], LedgerUnreachable] = (
        IOFailure(
            LedgerUnreachable(
                repo=".",
                argv="bd -C . list --status all --json",
                reason="query-unrunnable",
                detail="test double: no store configured",
            )
        )
        if snapshot is None
        else IOSuccess(snapshot)
    )

    def _read(*, repo: Path) -> IOResult[dict[str, str], LedgerUnreachable]:
        del repo  # The double answers for whatever repo it is handed.
        return answer

    assert hasattr(_role_key_gate, "bd_status_reader"), (
        "the `unarmed_until` arm must resolve its payload through the shared "
        "`checks/_work_item_liveness` resolver — a gate holding no resolver seam has "
        "no expiry at all, only the promise of one"
    )
    monkeypatch.setattr(_role_key_gate, "bd_status_reader", _read)
    _write_config(tmp_path=tmp_path, body=f'pure_trees = {{ unarmed_until = "{_LEDGER_ID}" }}\n')
    monkeypatch.chdir(tmp_path)

    code = public_api_result_typed.main()

    captured = capsys.readouterr()
    assert code == 0, (
        f"an `unarmed_until` declaration must parse and pass; "
        f"got exit={code} output={captured.out + captured.err!r}"
    )
    records = _records(captured=captured.out + captured.err)
    unarmed = [r for r in records if r.get(_SPELLING_FIELD) == "unarmed_until"]
    assert unarmed, f"the `unarmed_until` variant must be reported by name; got {records!r}"
    return unarmed[0]


def _records(*, captured: str) -> list[dict[str, object]]:
    """Parse the structlog JSON lines a check emitted.

    Deliberately unguarded: these checks emit ONE JSON object per line and
    nothing else, so a non-JSON line is a real regression in output discipline
    (`check-no-write-direct` bans stray writes) and should fail the test loudly
    rather than be skipped.
    """
    return [json.loads(line) for line in captured.splitlines()]


def test_legacy_empty_target_dirs_is_now_rejected_at_load(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Phase 4: a bare `target_dirs = []` no longer warns — it FAILS THE LOAD.

    This test previously asserted the Phase-1 behavior: still exit 0, but stop
    being silent. That WARN existed for one purpose — to make a previously
    INVISIBLE state countable before anyone migrated — and it has served it. All
    eight Python-bearing consumers migrated and measure zero, so the accepting
    loader's job is done; keeping it would leave the next author free to
    re-create the defect it was built to expose.

    `claude_md_coverage` is the sharpest case and the reason the WARN was worth
    building: it iterates `config.target_dirs` with NO gate at all, so a
    declared-empty value walked zero directories and exited 0 emitting NOTHING —
    strictly worse than `pure_trees`, which at least logged. Five of eight fleet
    repos were in that state.

    The REJECTION assertions below are the Phase-4 guarantee and are unchanged:
    the config does not load, the exit is non-zero, and the message names the
    key plus every legal spelling. What changed is only WHERE the reader finds
    that message. `livespec-dev-tooling-i6zi` supplied the rendering this
    docstring used to record as owed and filed separately — `main()` now catches
    `ConfigParseError` through the shared `_config_load.load_config_or_report`
    helper — so the message arrives as the `error` field of one structured
    event instead of as an interpreter traceback. Asserting it off the record
    rather than off `pytest.raises` is what keeps the rejection pinned across
    that move: the same key and the same four spellings must still reach the
    operator, and a check that swallowed them would fail here.
    """
    _write_config(tmp_path=tmp_path, body="target_dirs = []\n")
    monkeypatch.chdir(tmp_path)

    rc = claude_md_coverage.main()

    assert rc == 1, "a config that does not load must still exit non-zero"
    message = next(
        str(record.get("error"))
        for record in _records(captured=capsys.readouterr().err)
        if record.get("event") == "consumer config parse failed"
    )
    assert "target_dirs" in message
    # A rejection that does not say what IS legal only relocates the confusion.
    for spelling in ("not_applicable", "superseded_by", "unarmed_until", "convention_not_adopted"):
        assert spelling in message, spelling


def test_not_applicable_variant_parses_and_carries_its_reason(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`{ not_applicable = "<reason>" }` is accepted and its reason reaches the log.

    The whole point of the union is that the reason moves out of a TOML comment,
    which no checker can read, and into the parsed value. So the check must both
    accept the spelling and surface the reason it was given.
    """
    _write_config(
        tmp_path=tmp_path,
        body='pure_trees = { not_applicable = "flat-layout library has no pure-module subtree" }\n',
    )
    monkeypatch.chdir(tmp_path)

    code = public_api_result_typed.main()

    captured = capsys.readouterr()
    assert code == 0, (
        f"a blessed `not_applicable` declaration must parse and pass; "
        f"got exit={code} output={captured.out + captured.err!r}"
    )
    records = _records(captured=captured.out + captured.err)
    declared = [r for r in records if r.get(_SPELLING_FIELD) == "not_applicable"]
    assert declared, f"the `not_applicable` variant must be reported by name; got {records!r}"
    assert "flat-layout library has no pure-module subtree" in json.dumps(declared[0]), (
        f"the parsed REASON must reach the log — that is the point of moving it out "
        f"of a comment; got {declared[0]!r}"
    )


def test_unarmed_until_variant_is_warn_and_names_its_ledger_id(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`{ unarmed_until = "<ledger-id>" }` passes but at WARN, naming the id.

    `unarmed_until` is the ONLY variant with an expiry. It means "the concept
    applies here and is deliberately switched off pending named work" — meaning
    (B) in the classification — which is materially different from "does not
    apply". Two fleet repos are in this state on `pure_trees`, both citing
    `livespec-mutreal.1`, and both were indistinguishable from a flat-layout repo
    that genuinely has no pure tree. A distinct severity is what makes the
    deliberately-off case visible rather than merged into not-applicable.
    """
    record = _unarmed_record(
        tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys, snapshot=None
    )
    assert (
        record.get("level") == "warning"
    ), f"`unarmed_until` is a deferral and must be WARN, not info; got {record!r}"
    assert record.get("ledger_id") == "livespec-mutreal.1", (
        f"the ledger id must be surfaced so the deferral can be time-bounded; " f"got {record!r}"
    )


def test_unarmed_until_naming_a_closed_work_item_is_reported_as_a_conformance_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE FAIL CAPABILITY the promised expiry never had: a CLOSED payload is convicted.

    `SPECIFICATION/scenarios.md` §"Scenario: an unarmed-until payload naming a
    closed work item is a conformance failure" ratifies both the verdict and
    its wording — the report MUST identify the consumer, the key and the item,
    and MUST state that the declaration claims pending work that is already
    complete. Until the shared resolver was adopted here nothing in this
    library resolved the id against any tracker, so this branch was
    unreachable and a declaration could name work finished years ago while the
    key stayed switched off, silently, forever.
    """
    record = _unarmed_record(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        snapshot={_LEDGER_ID: "closed"},
    )
    assert record.get("level") == "error", (
        f"a stand-down on a CLOSED id must SURFACE; a warning here is the vacuous "
        f"gate this adoption exists to close; got {record!r}"
    )
    assert record.get("role") == "pure_trees", f"the failure must identify the KEY; {record!r}"
    assert (
        record.get("ledger_id") == _LEDGER_ID
    ), f"the failure must identify the ITEM; got {record!r}"
    assert record.get("consumer"), f"the failure must identify the CONSUMER; got {record!r}"
    assert (
        record.get("resolved_status") == "closed"
    ), f"the failure must name the item's RESOLVED STATUS; got {record!r}"
    assert "already complete" in str(record.get("event")), (
        f"the ratified wording is normative: the failure MUST state that the "
        f"declaration claims pending work that is already complete; got {record!r}"
    )


def test_unarmed_until_naming_an_open_work_item_stays_quiet(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The other direction: a payload naming genuinely pending work reads as it always did.

    `backlog` is deliberately the status under test. It is a legitimately OPEN
    state, and a resolver that flagged it would convict the majority of real
    declarations — the overshoot that gets a gate reverted within the hour
    rather than fixed.
    """
    record = _unarmed_record(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        snapshot={_LEDGER_ID: "backlog"},
    )
    assert record.get("level") == "warning", (
        f"an OPEN payload must stay quiet — the stand-down is honest and must not "
        f"read as a defect; got {record!r}"
    )
    assert (
        record.get("liveness_unverified") is None
    ), f"liveness WAS established here and must not report itself unverified; {record!r}"
    assert (
        record.get("resolved_status") == "backlog"
    ), f"backlog is an open state and must resolve as itself; got {record!r}"


def test_unarmed_until_skips_with_a_stated_reason_when_the_store_did_not_answer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE BRANCH THAT EXECUTES EVERYWHERE AND THAT NOBODY TESTS: no answer at all.

    Hosted CI and every sandbox reach no loopback ledger, so this is the
    path almost every run takes. The ratified exception admits exactly one
    way to proceed without an answer — a SKIP CARRYING ITS REASON — and
    forbids both the silent pass and the hard failure of an offline build.
    The `liveness_unverified` marker is what keeps an unverified answer from
    rendering like a verified one.
    """
    record = _unarmed_record(
        tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys, snapshot=None
    )
    assert (
        record.get("liveness_unverified") is True
    ), f"an unanswered store must SAY SO rather than pass silently; got {record!r}"
    assert (
        record.get("resolved_status") == "unreachable"
    ), f"the stated reason must name WHY the id could not be resolved; got {record!r}"
    assert record.get("level") == "warning", (
        f"an offline build must not be hard-failed for a condition its author "
        f"cannot fix; got {record!r}"
    )


def test_unarmed_until_naming_another_trackers_item_is_unverified_not_convicted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A cross-tracker citation is LEGITIMATE, so local absence must not convict it.

    `SPECIFICATION/contracts.md` §"Role keys" requires a verifier of this
    property to resolve identifiers ACROSS trackers, "since a consumer MAY
    legitimately cite a work item held in another repository's tracker; a
    verifier that resolves only within the declaring repo would reject valid
    declarations". Measured across the fleet on 2026-07-28, THREE of the four
    live payloads do exactly that — so reading absence-from-the-local-tenant
    as death would put three conformant repos in false breach on the day it
    shipped. This is the ONE place this gate reads the shared resolver more
    narrowly than `checks/no_todo_registry` does, and the asymmetry is the
    ratified clause rather than caution.
    """
    record = _unarmed_record(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        capsys=capsys,
        snapshot={"livespec-dev-tooling-someone-else": "ready"},
    )
    assert record.get("level") == "warning", (
        f"an id this repo's own store does not hold may live in another tracker; "
        f"convicting it would red a conformant repo; got {record!r}"
    )
    assert (
        record.get("liveness_unverified") is True
    ), f"the honest answer is UNVERIFIED, and it must say so; got {record!r}"
    assert (
        record.get("resolved_status") == "nonexistent"
    ), f"the diagnostic must name what the local store answered; got {record!r}"


def test_scalar_key_accepts_a_blessed_variant(*, tmp_path: Path) -> None:
    """The scalar keys take the SAME inline-table vocabulary as the list keys.

    `dataclasses_tree` and `neutral_hook_body_path` spell declared-none as `""`
    today. Sandbox-measured, that emptiness hides a live applicable concept just
    as `[]` does — a NewType-violating dataclass and a drifted hook body both
    survive behind it — so both keys are in the union's scope and must accept the
    same four spellings rather than growing a second vocabulary.
    """
    _write_config(
        tmp_path=tmp_path,
        body='dataclasses_tree = { not_applicable = "flat-layout library has no schema tree" }\n',
    )

    config = load_config(repo_root=tmp_path)

    assert type(config.dataclasses_tree).__name__ == "NotApplicable", (
        f"a scalar role key must accept the blessed inline-table spelling and parse to "
        f"the same variant type as a list key; got {config.dataclasses_tree!r}"
    )


def test_variant_with_empty_reason_is_rejected_at_load(*, tmp_path: Path) -> None:
    """A blessed spelling with an EMPTY reason is a hard load error, not a silent pass.

    Requiring a non-empty payload is what stops the union degenerating back into
    the defect it replaces: `{ not_applicable = "" }` would otherwise be a new
    unreadable emptiness wearing a blessed name.
    """
    _write_config(tmp_path=tmp_path, body='pure_trees = { not_applicable = "" }\n')

    with pytest.raises(ConfigParseError, match="not_applicable"):
        _ = load_config(repo_root=tmp_path)


def test_unknown_variant_name_is_rejected_and_names_the_blessed_spellings(
    *, tmp_path: Path
) -> None:
    """An inline table that is not one of the four blessed spellings fails loud.

    Without this, a typo (`not_aplicable`) would parse as some unknown-but-present
    table and could be mistaken for a declaration — the silent-consent shape all
    over again. The diagnostic must name the legal spellings, because a rejection
    that does not say what IS legal just relocates the confusion.
    """
    _write_config(tmp_path=tmp_path, body='pure_trees = { not_aplicable = "typo" }\n')

    with pytest.raises(ConfigParseError) as excinfo:
        _ = load_config(repo_root=tmp_path)

    message = str(excinfo.value)
    for spelling in (
        "not_applicable",
        "superseded_by",
        "unarmed_until",
        "convention_not_adopted",
    ):
        assert spelling in message, (
            f"the diagnostic must name every blessed spelling so the author can fix the "
            f"typo; `{spelling}` missing from {message!r}"
        )


def test_the_role_accessors_are_pure_and_total_with_no_announcement_inside(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """The accessors resolve a role and do NOTHING ELSE — no logging, no `bd`.

    The declared-absent announcement used to live inside these two bodies, and
    `unarmed_until` resolves its payload by spawning `bd`: that put a subprocess
    behind a `tuple[Path, ...]` return, a public function reaching the world while
    its type says it cannot.

    The PARAMETER assertions are the load-bearing half. Silence alone proves little
    — a populated role announces nothing either — whereas an accessor holding a
    `log` or a `check_id` is an accessor that CAN announce, whatever this particular
    call did. The shape is what keeps the seam separated; the silence only confirms
    it on the one input where an announcement would otherwise fire.
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    assert set(inspect.signature(_role_key_gate.resolve_role_trees).parameters) == {"role"}, (
        "`resolve_role_trees` must take the role and nothing else; a `log` or a "
        "`check_id` parameter is the announcement seam leaking back into the accessor"
    )
    assert set(inspect.signature(_role_key_gate.resolve_role_prefixes).parameters) == {"role"}, (
        "`resolve_role_prefixes` must take the role and nothing else; a `log` or a "
        "`check_id` parameter is the announcement seam leaking back into the accessor"
    )
    baseline = Config()

    trees = _role_key_gate.resolve_role_trees(role=baseline.pure_trees)
    prefixes = _role_key_gate.resolve_role_prefixes(role=baseline.source_tree_prefixes)

    assert trees == (), trees
    assert prefixes == (), prefixes
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", ""), (
        f"a pure accessor announces nothing, even for an undeclared role; got "
        f"{captured.out + captured.err!r}"
    )


def test_undeclared_baseline_announces_at_error_through_the_separated_seam(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """The defensive arm: a consumer reading a role off a bare `Config()` directly.

    `role_absence_exit_code` tests `declared_keys` FIRST and hard-errors there,
    so this arm is unreachable through the gate — which is exactly how the
    baseline's double meaning stayed invisible under `LegacyAmbiguousEmpty`. It
    is exercised deliberately rather than left uncovered: an unexercised arm is
    an arm nobody has read, and this one exists to make sure the honest state
    announces honestly if it is ever reached.

    ERROR, not WARN: an undeclared key is a configuration defect, never an
    opt-out, and it must not be able to read as one.

    Driven through the announcement SEAM rather than through an accessor. The
    announcement is the one part of a resolve step that reaches the world, so it
    rides a function of its own and the accessors beside it stay total — see
    `test_the_role_accessors_are_pure_and_total_with_no_announcement_inside`.
    """
    assert hasattr(_role_key_gate, "announce_role_absence"), (
        "the declared-absent announcement must ride a seam of its own — an accessor "
        "that announces is an accessor that can spawn `bd` behind a plain-tuple return"
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("undeclared_baseline_probe")

    _role_key_gate.announce_role_absence(
        role=Config().pure_trees, key="pure_trees", log=log, check_id="probe"
    )

    records = _records(captured=capsys.readouterr().err)
    announcement = [r for r in records if r.get("role") == "pure_trees"]
    assert announcement, records
    record = announcement[0]
    assert record.get("level") == "error", record
    assert record.get(_SPELLING_FIELD) == "undeclared", record
