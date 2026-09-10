"""Consumer-tier: the three `SPECIFICATION/scenarios.md` role-key PARSE scenarios.

Covers the declared-absence half of the union a consumer WRITES into its
`[tool.livespec_dev_tooling]` block, at the tier `scenarios.md` requires:

- **"a blessed declared-absent spelling parses to a distinct variant carrying its
  reason"** — each of the four spellings must resolve to a variant
  "distinguishable from every other declared-absent variant", and its payload
  must be "retrievable from the parsed value rather than requiring a reader to
  consult the TOML comment". Both halves are asserted against a fixture whose
  TOML comment DISAGREES with the inline-table payload, so a reader that took
  the comment would fail rather than accidentally agree.
- **"a declared-absent variant with an empty payload is rejected at load"** — a
  blessed NAME with an empty or whitespace-only payload is "a NEW unreadable
  emptiness wearing a blessed name", and loading must fail naming the key and
  every legal spelling.
- **"the legacy empty spelling on a union key is rejected at load"** — a bare
  `[]` / `""` fails with a `ConfigParseError` naming the key and every legal
  spelling, "And the emptiness MUST NOT be reported as a sanctioned opt-out".
  That last clause is the one a loader-only assertion cannot reach, so it is
  driven through a shipped check: the consumer-observable difference between a
  rejection and a sanctioned opt-out is whether the check announces a
  declared-absent variant and exits 0, or renders the parse failure and exits
  non-zero. The retired `legacy-ambiguous-empty` variant did the former.

The sibling `test_consumer_configuration_schema.py` registers the
`contracts.md` §"Consumer configuration schema" heading and asserts the SCHEMA
properties (one location, declaration-presence, the clean-key half). These are
the scenario-level parse outcomes, and neither file's assertions stand in for
the other's.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import public_api_result_typed
from livespec_dev_tooling.config import (
    BLESSED_ROLE_SPELLINGS,
    UNION_ROLE_KEYS,
    ConfigParseError,
    RoleAbsence,
    Undeclared,
    load_config,
    role_absence,
)
from tests.consumer.role_key_fixture import (
    LEGACY_EMPTY_SPELLINGS,
    ROLE_KEY_SPELLING_FIELD,
    records_from,
    union_key_block,
    write_consumer,
)

__all__: list[str] = []

pytestmark = pytest.mark.consumer

# The union key every fixture below declares absent. A TREE-valued key, so the
# legacy spelling under test is the bare `[]` the scenario names first.
_UNION_KEY = "pure_trees"
# The payload each blessed spelling carries. Deliberately distinct per spelling
# so a variant that dropped its payload cannot pass by matching a neighbour's.
_PAYLOADS: dict[str, str] = {
    "not_applicable": "no pure-module subtree exists in this layout",
    "superseded_by": "the pure layer is policed by the upstream package's own gate",
    "unarmed_until": "acme-widget-4211",
    "convention_not_adopted": "this repository declines the pure/impure split",
}
# The comment a reader must NOT be able to fall back to. It is written into
# every fixture ABOVE the key and contradicts the payload, so a reader
# consulting it produces a wrong answer rather than a coincidentally right one.
_DECOY_COMMENT = "# reason: THE COMMENT, WHICH NO CHECKER CAN READ"


def _payload_of(*, absence: RoleAbsence) -> object:
    """The payload the parsed variant carries, read off the VALUE it parsed to.

    Read as the variant's single dataclass field rather than through a
    per-spelling accessor, so this helper cannot itself encode the mapping the
    test is asserting. The TYPE distinctness — the scenario's "distinguishable
    from every other declared-absent variant" — is asserted separately, and a
    field-name-agnostic read here is what keeps the two claims independent:
    were all four spellings to collapse onto one class, this would still return
    the payload and the type assertion alone would convict.
    """
    fields = dataclasses.asdict(absence)
    assert len(fields) == 1, (
        f"each declared-absent variant carries exactly one field — its payload — so a "
        f"reader needs no per-variant knowledge to retrieve it; got {fields!r}"
    )
    return next(iter(fields.values()))


def test_each_blessed_spelling_parses_to_its_own_variant_carrying_its_own_payload(
    *, tmp_path: Path
) -> None:
    """Four spellings, four distinct variants, four payloads read off the value."""
    parsed = {
        spelling: role_absence(
            role=load_config(
                repo_root=write_consumer(
                    root=tmp_path / spelling,
                    block=union_key_block(
                        key=_UNION_KEY,
                        value=f'{{ {spelling} = "{payload}" }}',
                        comment=_DECOY_COMMENT,
                    ),
                )
            ).pure_trees
        )
        for spelling, payload in _PAYLOADS.items()
    }
    declared = {spelling: absence for spelling, absence in parsed.items() if absence is not None}
    assert sorted(declared) == sorted(_PAYLOADS), (
        f"every blessed spelling must resolve to a declared-absent variant rather than "
        f"to a populated value the consuming check would then scan; got {parsed}"
    )
    variants = {spelling: type(absence).__name__ for spelling, absence in declared.items()}
    assert len(set(variants.values())) == len(_PAYLOADS), (
        f"each spelling MUST resolve to a variant distinguishable from every other "
        f"declared-absent variant — collapsed onto one class, a gate can no longer tell "
        f"'the concept does not exist here' from 'switched off pending named work', "
        f"which is the whole distinction the union was introduced for; got {variants}"
    )
    assert Undeclared.__name__ not in set(variants.values()), (
        "a DECLARED absence must never parse to the parse-time `Undeclared` baseline — "
        f"that would spell a consumer's deliberate declaration as a silent omission; "
        f"got {variants}"
    )
    wrong = {
        spelling: _payload_of(absence=absence)
        for spelling, absence in declared.items()
        if _payload_of(absence=absence) != _PAYLOADS[spelling]
    }
    assert not wrong, (
        f"the payload MUST be retrievable from the parsed value rather than requiring a "
        f"reader to consult the TOML comment — each fixture's comment says "
        f"{_DECOY_COMMENT!r} and disagrees with its payload on purpose, so a reader that "
        f"fell back to the comment cannot pass by coincidence; wrong={wrong}"
    )


@pytest.mark.parametrize("spelling", sorted(_PAYLOADS))
@pytest.mark.parametrize("payload", ["", "   ", "\\t"])
def test_a_blessed_spelling_with_an_empty_payload_is_rejected_at_load(
    *, spelling: str, payload: str, tmp_path: Path
) -> None:
    """A blessed NAME does not launder an empty payload past the loader."""
    with pytest.raises(ConfigParseError) as rejected:
        _ = load_config(
            repo_root=write_consumer(
                root=tmp_path / "empty-payload",
                block=union_key_block(
                    key=_UNION_KEY, value=f'{{ {spelling} = "{payload}" }}', comment=_DECOY_COMMENT
                ),
            )
        )

    diagnostic = str(rejected.value)
    unnamed = [legal for legal in BLESSED_ROLE_SPELLINGS if legal not in diagnostic]
    assert _UNION_KEY in diagnostic and not unnamed, (
        f"loading MUST fail with an error naming the key and every legal spelling — an "
        f"empty payload under a blessed name is a new unreadable emptiness wearing a "
        f"legal name, and a remediation that does not say what IS legal only relocates "
        f"the confusion; unnamed={unnamed} diagnostic={diagnostic!r}"
    )


@pytest.mark.parametrize("key", sorted(UNION_ROLE_KEYS))
def test_the_legacy_empty_spelling_is_rejected_at_load_on_every_union_key(
    *, key: str, tmp_path: Path
) -> None:
    """Every union key, in ITS OWN empty spelling, one `ConfigParseError` naming it.

    The scenario's "a bare `[]` or `""`" is one spelling per key SHAPE, not two
    per key: `[]` is the retired empty for the collection-valued keys and `""`
    for the scalar-valued ones. Parametrizing over `UNION_ROLE_KEYS` rather than
    over a hand-listed set is what makes a key ADDED to the union arrive here
    already covered.
    """
    empty = LEGACY_EMPTY_SPELLINGS[key]
    with pytest.raises(ConfigParseError) as rejected:
        _ = load_config(
            repo_root=write_consumer(
                root=tmp_path / key,
                block=union_key_block(key=key, value=empty, comment=_DECOY_COMMENT),
            )
        )

    diagnostic = str(rejected.value)
    unnamed = [legal for legal in BLESSED_ROLE_SPELLINGS if legal not in diagnostic]
    assert key in diagnostic and not unnamed, (
        f"a bare `{empty}` on the UNION key `{key}` MUST fail at load with a "
        f"`ConfigParseError` naming the key AND every legal spelling; "
        f"unnamed={unnamed} diagnostic={diagnostic!r}"
    )


def test_a_shipped_check_renders_the_legacy_empty_as_a_rejection_not_a_sanctioned_opt_out(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The clause a loader-only assertion cannot reach, driven end to end.

    `public_api_result_typed` is the check whose disarming by the ambiguous
    spelling was MEASURED across nine fleet repositories, so it is the consumer
    this scenario is really about. Two observable properties separate a
    rejection from a sanctioned opt-out, and both are asserted: the exit is
    non-zero, and NO record announces a declared-absent variant — the retired
    `legacy-ambiguous-empty` variant announced itself exactly as the four
    blessed spellings do, and exited 0.
    """
    root = write_consumer(
        root=tmp_path / "legacy-empty",
        block=union_key_block(key=_UNION_KEY, value="[]", comment=_DECOY_COMMENT),
    )
    monkeypatch.chdir(root)

    code = public_api_result_typed.main()

    captured = capsys.readouterr()
    records = records_from(captured=captured.out + captured.err)
    assert code != 0, (
        f"a union key declared with the legacy empty spelling must REJECT — exiting 0 is "
        f"how the retired variant sanctioned it; got exit={code} records={records!r}"
    )
    announced = [record for record in records if ROLE_KEY_SPELLING_FIELD in record]
    assert not announced, (
        f"the emptiness MUST NOT be reported as a sanctioned opt-out: announcing it as a "
        f"declared-absent variant is precisely that report, and is what let one array "
        f"disarm this check across nine repositories; announced={announced!r}"
    )
    assert any(_UNION_KEY in str(record) for record in records), (
        f"the rendered failure must still name the offending key so the consumer knows "
        f"which declaration to fix; records={records!r}"
    )
