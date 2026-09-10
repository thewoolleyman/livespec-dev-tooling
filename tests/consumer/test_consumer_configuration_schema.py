"""Consumer-tier: the `SPECIFICATION/contracts.md` §"Consumer configuration schema".

The schema is the surface a consumer WRITES, so it is asserted through the
loader a consumer's checks read it with, against fixture trees under `tmp_path`
rather than against any one repo's opinions.

- **One location, no alternates.** "The library MUST NOT support alternate file
  locations (no `.livespec.jsonc` fallback, no env-var override)." Asserted by
  giving a fixture BOTH files, with a layout declared only in the `.livespec.jsonc`
  one: the loader must read the `pyproject.toml` block and nothing else.
- **`REQUIRED_ROLE_KEYS` is the single source of truth, and this consumer
  declares every member.** The section's declaration requirement is universal,
  and the constant is what each enforcing check reads "rather than restate the
  list; a second copy of the set is precisely the drift this contract exists to
  prevent". Asserted against this repository's own block — the self-application
  case §"Per-consumer pyproject declarations" names.
- **Declared-ness is recorded distinctly from value.** "Value alone cannot carry
  the distinction ... without recorded declaration-presence a check cannot tell a
  sanctioned opt-out from a silent omission — which is the whole distinction
  §"Role keys" rests on." Asserted with two fixtures whose parsed VALUES for a
  key are both empty and whose declaration-presence differs.
- **A bare `[]` / `""` on a UNION key is rejected at load, and stays legitimate
  on a CLEAN one.** The rejecting loader is the "unrepresentable-after-parse plus
  fail-loud-at-parse" guarantee, and the diagnostic "MUST name the offending key
  and every legal spelling for it" — a remediation that does not say what IS
  legal only relocates the confusion. The CLEAN half is asserted in the same test
  because reading "declared-empty is retired" as universal is the recorded
  regression: an empty `io_trees` exempts no directory, which makes its consuming
  checks STRICTER rather than blinder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling.config import (
    BLESSED_ROLE_SPELLINGS,
    REQUIRED_ROLE_KEYS,
    UNION_ROLE_KEYS,
    ConfigParseError,
    load_config,
    role_absence,
)

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]

# A complete, legal declaration of every required role key — the shape a
# consumer publishing its own block starts from.
_COMPLETE_BLOCK = """\
[tool.livespec_dev_tooling]
source_trees = ["src"]
io_trees = []
commands_trees = []
covered_trees = []
supervisor_entry_files = []
dataclasses_tree = { not_applicable = "fixture" }
pure_trees = { not_applicable = "fixture" }
source_tree_prefixes = { not_applicable = "fixture" }
target_dirs = { not_applicable = "fixture" }
neutral_hook_body_path = { not_applicable = "fixture" }
"""

# The same block with `io_trees` — a CLEAN key — omitted entirely. Its parsed
# value is empty either way; only declaration-presence differs.
_OMITTING_BLOCK = _COMPLETE_BLOCK.replace("io_trees = []\n", "")

# A layout declared in the file the schema says is NOT a configuration location.
_ALTERNATE_LOCATION = '{ "tool": { "livespec_dev_tooling": { "source_trees": ["decoy"] } } }'

_UNION_KEY = "pure_trees"
_CLEAN_KEY = "io_trees"


def _fixture(*, root: Path, block: str, livespec_jsonc: str | None = None) -> Path:
    """A consumer tree carrying `block`, and optionally a decoy `.livespec.jsonc`."""
    root.mkdir(parents=True, exist_ok=True)
    _ = root.joinpath("pyproject.toml").write_text(block, encoding="utf-8")
    if livespec_jsonc is not None:
        _ = root.joinpath(".livespec.jsonc").write_text(livespec_jsonc, encoding="utf-8")
    return root


def test_the_role_key_schema_is_read_from_one_location_and_records_declaration_presence(
    *, tmp_path: Path
) -> None:
    """The block governs alone, and a declared-absent key is distinguishable from an omitted one."""
    declared = load_config(
        repo_root=_fixture(
            root=tmp_path / "declared",
            block=_COMPLETE_BLOCK,
            livespec_jsonc=_ALTERNATE_LOCATION,
        )
    )
    assert declared.source_trees == (Path("src"),), (
        f"the `[tool.livespec_dev_tooling]` block in `pyproject.toml` is the single "
        f"configuration location — no `.livespec.jsonc` fallback — so the decoy layout "
        f"must not reach the loader; got {declared.source_trees}"
    )

    omitted = load_config(repo_root=_fixture(root=tmp_path / "omitted", block=_OMITTING_BLOCK))
    assert omitted.io_trees == declared.io_trees, (
        "the fixture pair must differ ONLY in declaration-presence, so their parsed "
        f"values must agree; got {omitted.io_trees} vs {declared.io_trees}"
    )
    assert (_CLEAN_KEY in declared.declared_keys, _CLEAN_KEY in omitted.declared_keys) == (
        True,
        False,
    ), (
        "value alone cannot carry the distinction between a sanctioned opt-out and a "
        "silent omission, so the loader must record WHICH keys were declared; got "
        f"declared={sorted(declared.declared_keys)} omitted={sorted(omitted.declared_keys)}"
    )
    assert role_absence(role=declared.pure_trees) is not None, (
        "a declared-absent UNION key must parse to a declared-absent variant rather "
        "than to a populated value the consuming check would then scan"
    )


def test_this_consumer_declares_every_required_role_key() -> None:
    """The self-application case: every member of `REQUIRED_ROLE_KEYS` is declared here."""
    assert REQUIRED_ROLE_KEYS, "the loader must export a non-empty required role-key set"
    config = load_config(repo_root=_REPO_ROOT)
    undeclared = sorted(REQUIRED_ROLE_KEYS - config.declared_keys)
    assert not undeclared, (
        f"the declaration requirement is universal and `REQUIRED_ROLE_KEYS` is its single "
        f"source of truth, so this consumer's own block must declare every member — a "
        f"wired check gating on an undeclared key hard-errors; undeclared={undeclared}"
    )


def test_a_bare_empty_is_rejected_on_a_union_key_and_remains_legal_on_a_clean_one(
    *, tmp_path: Path
) -> None:
    """The ambiguous spelling fails loud at parse; the exemption spelling does not."""
    ambiguous = _COMPLETE_BLOCK.replace(
        f'{_UNION_KEY} = {{ not_applicable = "fixture" }}', f"{_UNION_KEY} = []"
    )

    with pytest.raises(ConfigParseError) as rejected:
        _ = load_config(repo_root=_fixture(root=tmp_path / "ambiguous", block=ambiguous))

    diagnostic = str(rejected.value)
    unnamed = [spelling for spelling in BLESSED_ROLE_SPELLINGS if spelling not in diagnostic]
    assert _UNION_KEY in diagnostic and not unnamed, (
        f"the diagnostic MUST name the offending key and EVERY legal spelling for it — a "
        f"remediation that does not say what IS legal only relocates the confusion; "
        f"unnamed={unnamed} diagnostic={diagnostic!r}"
    )
    assert _CLEAN_KEY not in UNION_ROLE_KEYS, (
        f"`{_CLEAN_KEY}` scopes an exemption rather than a scan universe, so it is a "
        f"CLEAN key and its bare `[]` must stay legitimate"
    )

    clean = load_config(repo_root=_fixture(root=tmp_path / "clean", block=_COMPLETE_BLOCK))
    assert clean.io_trees == (), (
        f'"declared-empty is retired" MUST NOT be read as universal: an empty '
        f"`{_CLEAN_KEY}` exempts no directory, which makes its consuming checks "
        f"stricter rather than blinder; got {clean.io_trees}"
    )
