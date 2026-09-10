"""Consumer-tier: the `SPECIFICATION/contracts.md` §"Consumer compat block — pin-and-bump policy".

The section owns the release-level coordination policy, and the part of it a
consumer both WRITES and is judged on is the `compat` block: a top-level section
in `.livespec.jsonc` keyed by the consumer's OWN plugin / library name, carrying
`livespec` (a semver range) and `pinned` (the release tag it currently runs
against). This library is itself a consumer (§"Self-hosting"), so its own block
is the case under test — the section names it as one of the shapes the policy
binds.

Four properties, each failing independently:

- **Both REQUIRED fields are present, under the consumer's own name.** A block
  keyed by anything else is invisible to the pin-autodiscovery walk that
  rewrites it, so the bump-pin PR would edit nothing and report success.
- **`pinned` names a concrete release tag.** "Every consumer pins. Each
  consumer's automation and autonomous workflows MUST run against the pinned
  `livespec` release, NEVER against HEAD. Running against HEAD bypasses the
  audited coordination mechanism and is an out-of-contract operation." A moving
  ref (`master`, `main`, `HEAD`) in this field IS that out-of-contract state,
  and it is a state this file has held before — the block's own comment records
  the bootstrap period when `pinned` was `"master"`.
- **The block carries only non-sensitive version metadata.** "`.livespec.jsonc`
  MUST NOT carry secrets; the `compat` block contains only non-sensitive version
  metadata." Asserted as an exact field set rather than as a keyword scan: a
  field this contract does not name is one no reader of the contract expects to
  find in a committed, world-readable file.
- **The declared block is what the automation actually discovers.** "This is the
  same block shape the pin-autodiscovery walk recognizes per §"Pin autodiscovery
  rules"." Asserted by running the shipped walk over this repository and
  requiring a record whose `pin_key` is this consumer's own name and whose
  `current_value` is byte-equal to the declared `pinned`. That is the join
  between the schema and the mechanism, and it is where a correctly-written
  block and a walk that cannot see it would otherwise both look fine.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

import jsoncomment
import pytest
from returns.io import IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.cross_repo.pin_autodiscovery import discover

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVESPEC_JSONC = _REPO_ROOT / ".livespec.jsonc"

# This consumer's own library name — the top-level key the section requires the
# block to be filed under.
_CONSUMER_NAME = "livespec-dev-tooling"

# The two REQUIRED fields, and the exact set the block may carry.
_COMPAT_FIELDS = frozenset({"livespec", "pinned"})

# A concrete release tag, as opposed to a moving branch alias.
_RELEASE_TAG = re.compile(r"^v\d+\.\d+\.\d+")

# The walk's own name for the format this block is discovered as.
_PIN_FORMAT = "livespec_jsonc_compat_pinned"
_PIN_SOURCE_REPO = "livespec"


def _compat_block() -> dict[str, object]:
    """This consumer's own `compat` block, parsed from `.livespec.jsonc`."""
    parsed = cast(
        "dict[str, dict[str, dict[str, object]]]",
        jsoncomment.loads(_LIVESPEC_JSONC.read_text(encoding="utf-8")),
    )
    assert _CONSUMER_NAME in parsed, (
        f"the `compat` block MUST be filed under a top-level key named for the consumer "
        f"itself (`{_CONSUMER_NAME}`); top-level keys={sorted(parsed)}"
    )
    section = parsed[_CONSUMER_NAME]
    assert "compat" in section, f"`{_CONSUMER_NAME}` must carry a `compat` block"
    return section["compat"]


def _discovered_pins() -> list[dict[str, str]]:
    """Every livespec-sourced pin the shipped autodiscovery walk finds here."""
    walked = discover(root=_REPO_ROOT, source_repo=_PIN_SOURCE_REPO)
    assert isinstance(
        walked, IOSuccess
    ), f"the pin-autodiscovery walk must complete over this repository; got {walked}"
    return unsafe_perform_io(walked.unwrap())


def test_this_consumers_compat_block_declares_both_required_fields_and_carries_no_more() -> None:
    """The block's field set is exactly the two non-sensitive version fields."""
    compat = _compat_block()

    missing = sorted(_COMPAT_FIELDS - set(compat))
    assert not missing, (
        f"`livespec` (the supported semver range) and `pinned` (the tag currently run "
        f"against) are both REQUIRED; missing={missing}"
    )
    extra = sorted(set(compat) - _COMPAT_FIELDS)
    assert not extra, (
        f"the block contains only non-sensitive version metadata and MUST NOT carry "
        f"secrets, so a field this contract does not name has no reader that expects it "
        f"in a committed file; extra={extra}"
    )
    assert isinstance(compat["livespec"], str) and compat["livespec"], (
        f"`livespec` must be a non-empty semver RANGE describing the supported versions; "
        f"got {compat['livespec']!r}"
    )


def test_the_pinned_release_is_a_concrete_tag_the_autodiscovery_walk_finds() -> None:
    """`pinned` names a release, never HEAD, and the walk that rewrites it sees it."""
    pinned = _compat_block()["pinned"]
    assert isinstance(pinned, str) and _RELEASE_TAG.match(pinned), (
        f"every consumer's automation MUST run against a pinned RELEASE, never against "
        f"HEAD or a moving branch alias — that bypasses the audited coordination "
        f"mechanism and is an out-of-contract operation; got {pinned!r}"
    )

    own = [
        record
        for record in _discovered_pins()
        if record["pin_format"] == _PIN_FORMAT and record["pin_key"] == _CONSUMER_NAME
    ]
    assert own, (
        f"the declared block must be the shape the pin-autodiscovery walk recognizes, or "
        f"the bump-pin PR rewrites nothing and reports success; discovered="
        f"{[record['pin_key'] for record in _discovered_pins()]}"
    )
    values = sorted({record["current_value"] for record in own})
    assert values == [pinned], (
        f"the walk's `current_value` is what the bump rewrites FROM, so it must be the "
        f"declared pin byte-for-byte; got {values} declared={pinned!r}"
    )
