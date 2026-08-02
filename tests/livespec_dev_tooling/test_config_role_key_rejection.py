"""Phase 4 of `livespec-dev-tooling-8o8e.1` — the loader REJECTS the ambiguous spelling.

Phases 1-3 made the ambiguity visible, migrated every consumer off it, and made
the migrated state a standing guarantee. This is the phase that makes
`SPECIFICATION` v033's "the loader MUST reject it as a hard load-time error"
true, which is the half of the closure precondition that has been false since
the epic opened.

Two properties are pinned here and they pull in opposite directions, which is
why they live in one module: `[]` / `""` must be REJECTED on the five UNION
keys, and must remain LEGITIMATE on the five CLEAN keys. A blanket rejection
would be a spec violation now that the carve-out is ratified
(v033 section "Clean role keys retain `[]`"), and it would be wrong in exactly the
half of cases nobody would think to test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling import config as config_module
from livespec_dev_tooling.config import (
    BLESSED_ROLE_SPELLINGS,
    REQUIRED_ROLE_KEYS,
    UNION_ROLE_KEYS,
    Config,
    ConfigParseError,
    load_config,
    role_absence,
)

__all__: list[str] = []


_SCALAR_UNION_KEYS = frozenset({"dataclasses_tree", "neutral_hook_body_path"})
_CLEAN_KEYS = REQUIRED_ROLE_KEYS - UNION_ROLE_KEYS


def _write_block(*, root: Path, body: str) -> None:
    _ = (root / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{body}", encoding="utf-8"
    )


@pytest.mark.parametrize("key", sorted(UNION_ROLE_KEYS))
def test_legacy_empty_on_a_union_key_is_a_hard_load_error(*, key: str, tmp_path: Path) -> None:
    """The ambiguous spelling no longer parses at all.

    Phase 1 accepted it with a WARN so the previously-invisible state could be
    counted before anyone migrated. All eight Python-bearing consumers have
    migrated and measure zero, so the transitional allowance has done its work
    and keeping it would leave the next author free to re-create the defect.
    """
    spelling = '""' if key in _SCALAR_UNION_KEYS else "[]"
    _write_block(root=tmp_path, body=f"{key} = {spelling}\n")

    with pytest.raises(ConfigParseError) as excinfo:
        _ = load_config(repo_root=tmp_path)

    message = str(excinfo.value)
    assert key in message
    # A rejection that does not say what IS legal only relocates the confusion,
    # so every blessed spelling is named inline.
    for spelling_name in BLESSED_ROLE_SPELLINGS:
        assert spelling_name in message, spelling_name


@pytest.mark.parametrize("key", sorted(_CLEAN_KEYS))
def test_empty_on_a_clean_key_still_parses(*, key: str, tmp_path: Path) -> None:
    """The ratified carve-out: `[]` is legitimate for an exemption/severity predicate.

    Their consuming checks derive the universe from `resolve_check_universe()`
    and read the key only to decide what is EXEMPT, so emptiness makes them
    STRICTER rather than blinder. Rejecting here would wholesale-exempt nothing
    and break five repos for a defect they do not have.
    """
    _write_block(root=tmp_path, body=f"{key} = []\n")

    config = load_config(repo_root=tmp_path)

    assert key in config.declared_keys
    assert getattr(config, key) == ()


def test_the_legacy_variant_is_gone_from_the_domain_model() -> None:
    """`LegacyAmbiguousEmpty` must not merely be unreachable — it must not exist.

    An unreachable-but-present variant is the shape this epic exists to remove:
    it stays available to the next author, and `assert_never` keeps accepting it
    at every match site.
    """
    assert not hasattr(config_module, "LegacyAmbiguousEmpty")
    assert "LegacyAmbiguousEmpty" not in config_module.__all__


def test_an_undeclared_key_is_its_own_variant_not_a_borrowed_spelling() -> None:
    """The defect the Phase 4 measurement surfaced, pinned so it cannot return.

    `LegacyAmbiguousEmpty` carried BOTH "the consumer declared `[]`" and "the
    consumer never declared anything", because the five `_BASELINE_*` constants
    bound it for a bare `Config()`. Two incompatible meanings in one value,
    inside the type introduced to make exactly that unrepresentable — measured
    on `livespec-console-beads-fabro`, which has no `[tool.livespec_dev_tooling]`
    block at all and reported five of them.

    Reusing `NotApplicable` for the baseline would be the tempting one-liner and
    is the wrong fix: it writes a FALSEHOOD into parsed data for every consumer
    without a block.
    """
    undeclared = getattr(config_module, "Undeclared", None)
    assert undeclared is not None, "the baseline needs its own variant, not a borrowed one"
    assert "Undeclared" in config_module.__all__

    baseline = Config()
    assert baseline.declared_keys == frozenset()
    for key in sorted(UNION_ROLE_KEYS):
        absence = role_absence(role=getattr(baseline, key))
        assert isinstance(absence, undeclared), key
        assert absence.key == key
