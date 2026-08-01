"""`RowSkip` means NOT EVALUABLE only; inapplicability is an excluded pass.

`livespec-dev-tooling-8o8e.2`, and v181 condition 3 — a variant one consumer
reads as "not evaluable" and another reads as "not applicable" is a sentinel
wearing a type annotation, not a discriminated union.

THE CONSEQUENCE IS LIVE, NOT THEORETICAL. The central lane feeds every
`RowSkip` into `blind_rows`, whose own module docstring leaves no way out:
"There is no lever, env var, exemption list, or opt-out: a lane that owns a row
it could not read exits non-zero, always." `beads-tenant-connection-consistency`
is REGISTERED, and returned `RowSkip` for two INAPPLICABILITIES — a member that
is simply not beads-backed. So the moment the beads-backed population among
applicable members reaches zero, that row goes blind and reds master fleet-wide
for a condition that is not a failure. Today's `blind_rows: 0` is contingent on
at least one applicable member still evaluating.

⛔ THE POSITIVE CONTROL IS THE LOAD-BEARING TEST IN THIS FILE.
`test_unreadable_beads_config_is_still_a_skip` asserts a genuine can't-read
STAYS a `RowSkip`. Without it, an implementation that turned EVERY skip into a
pass would satisfy every other assertion here while destroying the blind-row
signal entirely — trading a fail-closed defect for a fail-open one and calling
it a fix.
"""

from __future__ import annotations

from test_rows_beads import (
    _BEADS_ARGS,
    _JSONC_ARGS,
    _MEMBER,
    _beads_config,
    _livespec_jsonc,
    _ok,
    make_context,
)

from livespec_dev_tooling.fleet._context import (
    EXCLUDED_NOTE_PREFIX,
    GhResult,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_beads import assert_tenant_connection_consistency

__all__: list[str] = []


def test_member_without_dolt_keys_is_excluded_not_blind() -> None:
    """Not beads-backed is INAPPLICABLE — a definitive non-obligation."""
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text="issues:\n  prefix: widget\n"),
            _JSONC_ARGS: _ok(text=_livespec_jsonc()),
        }
    )

    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowPass), (
        "a member that is not beads-backed is INAPPLICABLE, not unevaluable; "
        "a RowSkip here feeds blind_rows and reds master fleet-wide once the "
        "beads-backed population reaches zero"
    )
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)
    assert "dolt" in outcome.note


def test_member_without_connection_block_is_excluded_not_blind() -> None:
    """No impl-plugin connection block is likewise a definitive non-obligation."""
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text=_beads_config()),
            _JSONC_ARGS: _ok(text=_livespec_jsonc(with_connection=False)),
        }
    )

    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)
    assert "connection block" in outcome.note


def test_unreadable_beads_config_is_still_a_skip() -> None:
    """THE POSITIVE CONTROL — a genuine can't-read must NOT become a pass.

    Without this, turning every skip into a pass satisfies the rest of this
    file while destroying the blind-row signal the central lane exists to
    raise. The fix narrows what `RowSkip` MEANS; it must not empty it.
    """
    ctx = make_context(
        table={
            _BEADS_ARGS: GhResult(returncode=1, stdout="", stderr="unreadable"),
            _JSONC_ARGS: _ok(text=_livespec_jsonc()),
        }
    )

    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)

    assert isinstance(outcome, RowSkip), (
        "a read that did not happen is still NOT EVALUABLE and must keep " "feeding blind_rows"
    )
