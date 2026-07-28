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
from livespec_dev_tooling.config import Config, ConfigParseError, load_config

# The structured field every declared-absent announcement carries, naming the
# variant the consumer declared.
_SPELLING_FIELD = "role_key_spelling"

__all__: list[str] = []


def _write_config(*, tmp_path: Path, body: str) -> None:
    """Overwrite the fixture-seeded config with exactly the block under test."""
    _ = tmp_path.joinpath("pyproject.toml").write_text(
        f'[project]\nname = "consumer"\nversion = "0.0.0"\n\n'
        f"[tool.livespec_dev_tooling]\n{body}",
        encoding="utf-8",
    )


def _records(*, captured: str) -> list[dict[str, object]]:
    """Parse the structlog JSON lines a check emitted.

    Deliberately unguarded: these checks emit ONE JSON object per line and
    nothing else, so a non-JSON line is a real regression in output discipline
    (`check-no-write-direct` bans stray writes) and should fail the test loudly
    rather than be skipped.
    """
    return [json.loads(line) for line in captured.splitlines()]


def test_legacy_empty_target_dirs_is_now_rejected_at_load(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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

    What is asserted is the LOADER guarantee, because that is what Phase 4
    delivers: the config does not load, and the error names the key plus every
    legal spelling. The check's `main()` does NOT yet wrap it in a structured
    diagnostic — 30 of 31 checks reading `load_config` lack that catch, which
    Phase 4 makes reachable for the first time and which is filed separately.
    The exception is loud and non-zero either way; it is the RENDERING that is
    owed, not the rejection.
    """
    _write_config(tmp_path=tmp_path, body="target_dirs = []\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigParseError) as excinfo:
        _ = claude_md_coverage.main()

    message = str(excinfo.value)
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
    _write_config(tmp_path=tmp_path, body='pure_trees = { unarmed_until = "livespec-mutreal.1" }\n')
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
    assert (
        unarmed[0].get("level") == "warning"
    ), f"`unarmed_until` is a deferral and must be WARN, not info; got {unarmed[0]!r}"
    assert unarmed[0].get("ledger_id") == "livespec-mutreal.1", (
        f"the ledger id must be surfaced so the deferral can be time-bounded; "
        f"got {unarmed[0]!r}"
    )


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


def test_undeclared_baseline_announces_at_error_when_reached_off_the_gate(
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
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("undeclared_baseline_probe")

    trees = _role_key_gate.resolve_role_trees(
        role=Config().pure_trees, key="pure_trees", log=log, check_id="probe"
    )

    assert trees == ()
    records = _records(captured=capsys.readouterr().err)
    announcement = [r for r in records if r.get("role") == "pure_trees"]
    assert announcement, records
    record = announcement[0]
    assert record.get("level") == "error", record
    assert record.get(_SPELLING_FIELD) == "undeclared", record
