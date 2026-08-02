"""Tests for `pin_staleness` — which discovered pins the freshness scan checks.

The defect these pin down (work-item `livespec-dev-tooling-p73`): the freshness
workflow collapsed every record for a source to ONE representative
(`.[0].current_value`), so a source whose FIRST record was fresh never produced a
bump PR even when its other records were stale. `SPECIFICATION/contracts.md`
section "Reusable workflow inventory" already requires a bump PR per
`(source_repo, current_pin, latest_tag)` triple, so the contract was right and
the implementation was not.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from livespec_dev_tooling.cross_repo.pin_staleness import (
    denotes_same_release,
    distinct_source_pins,
    main,
    ordinal_distance,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_ROOT = _REPO_ROOT / "livespec_dev_tooling"
_FRESHNESS_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "reusable-pin-freshness.yml"


def _record(*, source_repo: str, current_value: str, file_path: str) -> dict[str, str]:
    return {
        "pin_format": "fabro_sandbox_docker_image",
        "file_path": file_path,
        "pin_key": "ghcr.io/thewoolleyman/livespec-fabro-sandbox",
        "current_value": current_value,
        "source_repo": source_repo,
    }


def test_distinct_source_pins_keeps_every_distinct_pin_not_only_the_first() -> None:
    """The exact shape that hid the drift: a FRESH first record masking stale ones.

    `livespec-dev-tooling` pinned the fabro image fresh in its Fabro
    `workflow.toml` while its `.github/workflows/ci.yml` sat six releases behind.
    Taking `.[0]` saw only the fresh value and emitted no bump PR at all.
    """
    records = [
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.49.2",
            file_path=".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml",
        ),
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.43.2",
            file_path=".github/workflows/ci.yml",
        ),
    ]

    assert distinct_source_pins(records=records) == [
        ("livespec-dev-tooling", "python-v0.43.2"),
        ("livespec-dev-tooling", "python-v0.49.2"),
    ]


def test_distinct_source_pins_deduplicates_repeated_identical_pins() -> None:
    """Several jobs pinning the SAME tag are ONE pin to check, not N.

    A cut-over consumer repeats the `container:` block per job, so the same
    `(source, value)` pair recurs; checking it once keeps the log and any
    resulting PR set proportional to distinct pins rather than to job count.
    """
    records = [
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.43.2",
            file_path=".github/workflows/ci.yml",
        )
        for _ in range(5)
    ]

    assert distinct_source_pins(records=records) == [("livespec-dev-tooling", "python-v0.43.2")]


def test_distinct_source_pins_separates_distinct_sources_and_sorts() -> None:
    """Pairs are sorted so iteration order is deterministic, not walk-order."""
    records = [
        _record(
            source_repo="livespec-runtime",
            current_value="v0.3.0",
            file_path="pyproject.toml",
        ),
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.49.2",
            file_path=".github/workflows/ci.yml",
        ),
    ]

    assert distinct_source_pins(records=records) == [
        ("livespec-dev-tooling", "python-v0.49.2"),
        ("livespec-runtime", "v0.3.0"),
    ]


def test_distinct_source_pins_is_empty_for_no_records() -> None:
    assert distinct_source_pins(records=[]) == []


@pytest.mark.parametrize(
    "malformed",
    [
        {"source_repo": "livespec-runtime"},
        {"current_value": "v0.3.0"},
        {"source_repo": "", "current_value": "v0.3.0"},
        {"source_repo": "livespec-runtime", "current_value": ""},
    ],
)
def test_distinct_source_pins_skips_a_malformed_record_without_raising(
    *, malformed: dict[str, str]
) -> None:
    """A malformed record is skipped, never fatal.

    The walk is contract-bound to tolerate unrecognized formats, so one bad
    record must not abort the freshness scan for every other pin.
    """
    good = _record(
        source_repo="livespec-dev-tooling",
        current_value="python-v0.43.2",
        file_path=".github/workflows/ci.yml",
    )

    assert distinct_source_pins(records=[malformed, good]) == [
        ("livespec-dev-tooling", "python-v0.43.2")
    ]


def test_main_emits_every_distinct_pin_as_json(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.49.2",
            file_path=".claude-plugin/.fabro/workflows/implement-work-item/workflow.toml",
        ),
        _record(
            source_repo="livespec-dev-tooling",
            current_value="python-v0.43.2",
            file_path=".github/workflows/ci.yml",
        ),
    ]
    monkeypatch.setenv("RECORDS", json.dumps(records))

    assert main() == 0

    assert json.loads(capsys.readouterr().out) == [
        {"source_repo": "livespec-dev-tooling", "current_value": "python-v0.43.2"},
        {"source_repo": "livespec-dev-tooling", "current_value": "python-v0.49.2"},
    ]


def test_main_defaults_to_an_empty_record_set(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An absent RECORDS env yields an empty list, not a crash."""
    monkeypatch.delenv("RECORDS", raising=False)

    assert main() == 0
    assert json.loads(capsys.readouterr().out) == []


# `ordinal_distance` — work-item `livespec-dev-tooling-ews`. The freshness scan
# used to compute this in shell, where an early `awk` exit SIGPIPEd the upstream
# producer; under `pipefail` that made the whole pipeline non-zero, so the
# `||` fallback ALSO ran and the substitution captured TWO values. The numeric
# comparison then syntax-errored, evaluated false, and silently dropped a stale
# source. See the regression test below for the full shell form and why the
# failure mode is inverted from safe.


def test_ordinal_distance_counts_releases_back_to_the_current_tag() -> None:
    tags = ["v0.49.2", "v0.49.1", "v0.49.0", "v0.48.2", "v0.47.0", "v0.46.5"]

    assert ordinal_distance(tags=tags, current="v0.46.5", fallback=1) == 5


def test_ordinal_distance_is_zero_when_the_pin_is_the_latest_release() -> None:
    tags = ["v0.49.2", "v0.49.1"]

    assert ordinal_distance(tags=tags, current="v0.49.2", fallback=1) == 0


def test_ordinal_distance_falls_back_when_the_tag_is_absent() -> None:
    """An unrecognizable pin (e.g. a pre-layer `sha-` tag) must not read as fresh."""
    tags = ["v0.49.2", "v0.49.1"]

    assert ordinal_distance(tags=tags, current="sha-deadbeef", fallback=7) == 7


def test_ordinal_distance_falls_back_on_an_empty_tag_list() -> None:
    assert ordinal_distance(tags=[], current="v0.49.2", fallback=3) == 3


def test_ordinal_distance_reads_every_tag_rather_than_stopping_at_the_match() -> None:
    """The regression guard for the SIGPIPE defect.

    The shell form was::

        ordinal_distance=$(gh release list ... \
          | awk -v current="$current" '{if($0==current){print n; exit} n++}' \
          || echo "$STALENESS_THRESHOLD")

    awk's early `exit` closed the pipe, `gh` took SIGPIPE, and under `pipefail`
    the PIPELINE went non-zero — so the `|| echo` fallback ALSO ran and the
    command substitution captured BOTH values ("9\n1"). The arithmetic then
    syntax-errored and evaluated FALSE, silently dropping a stale source.

    The failure mode is inverted from safe: the early exit only fires when the
    current tag IS found, i.e. the normal stale case the scan exists to catch.
    Consuming the WHOLE list makes the pure function total and the CLI immune by
    construction — there is no early exit for a producer to trip over.
    """
    tags = [f"v9.9.{index}" for index in range(5000)]
    tags.append("v0.1.0")

    assert ordinal_distance(tags=tags, current="v9.9.3", fallback=1) == 3
    assert ordinal_distance(tags=tags, current="v0.1.0", fallback=1) == 5000


def test_main_ordinal_distance_mode_prints_a_bare_integer(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CLI must emit ONE integer and nothing else.

    This is the property whose absence caused the outage: the shell captured two
    values and the arithmetic silently evaluated false. A caller must be able to
    feed this straight into a numeric comparison.
    """
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO("v0.49.2\nv0.49.1\nv0.49.0\n"),
    )
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--ordinal-distance", "v0.49.0", "1"])

    assert main() == 0

    out = capsys.readouterr().out
    assert out.splitlines() == ["2"]
    assert int(out.strip()) == 2


def test_main_ordinal_distance_mode_emits_the_fallback_for_an_absent_tag(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("v0.49.2\nv0.49.1\n"))
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--ordinal-distance", "sha-old", "4"])

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["4"]


def test_main_ordinal_distance_mode_ignores_blank_lines(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A trailing newline from the producer must not shift the distance."""
    monkeypatch.setattr("sys.stdin", io.StringIO("v0.49.2\n\nv0.49.1\n\n"))
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--ordinal-distance", "v0.49.1", "1"])

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["1"]


# `denotes_same_release` — work-item `livespec-dev-tooling-clrk`. The freshness
# scan decided pin currency with raw string equality on the tag bytes
# (`[[ "$current" == "$latest" ]]`), which is correct only for pin formats whose
# value IS a bare release tag. The `fabro_sandbox_docker_image` format's value is
# a LAYER-PREFIXED image tag over the bare release version, so it compared
# unequal even at the same release and was reported stale BY CONSTRUCTION on
# every sweep, forever. Measured in the 2026-07-20 sweep (livespec job
# 88389908424), where the prefixed pin misreported while two unprefixed pins in
# the SAME run evaluated correctly:
#
#     ##[notice]livespec stale: current=v0.18.0 latest=v0.18.4 distance=4
#     ##[notice]livespec-dev-tooling stale: current=python-v0.50.8 latest=v0.50.8 distance=1
#     ##[notice]livespec-runtime pinned at v0.11.0, already current


def test_denotes_same_release_matches_a_layer_prefixed_pin_at_the_latest_version() -> None:
    """The defect itself: `python-v0.50.8` and `v0.50.8` ARE the same release.

    Raw equality said otherwise, so this pin could never be reported current no
    matter how many bump PRs the sweep merged.
    """
    assert denotes_same_release(pinned_tag="python-v0.50.8", release_tag="v0.50.8") is True


@pytest.mark.parametrize(
    "pinned_tag",
    [
        "base-v0.51.4",
        "python-v0.51.4",
        "python-agent-v0.51.4",
        "python-rust-v0.51.4",
        "python-rust-agent-v0.51.4",
    ],
)
def test_denotes_same_release_matches_every_published_layer_prefix(*, pinned_tag: str) -> None:
    """All five layers `fabro-sandbox-image.yml` publishes share the one version anchor.

    The layer a pin selects is orthogonal to whether it is CURRENT: a `base-`
    pin at the newest release is exactly as current as a `python-rust-agent-` one.
    """
    assert denotes_same_release(pinned_tag=pinned_tag, release_tag="v0.51.4") is True


def test_denotes_same_release_rejects_a_layer_prefixed_pin_behind_the_latest() -> None:
    """Fixing the false-stale must not create a false-fresh.

    A prefixed pin genuinely behind still has to read as stale, or the fix would
    trade a permanently-open bump loop for a silently-unmaintained pin.
    """
    assert denotes_same_release(pinned_tag="python-v0.50.7", release_tag="v0.50.8") is False


@pytest.mark.parametrize(
    ("pinned_tag", "release_tag", "expected"),
    [
        ("v0.11.0", "v0.11.0", True),
        ("v0.18.0", "v0.18.4", False),
        ("v0.50.8", "v0.50.8", True),
    ],
)
def test_denotes_same_release_leaves_unprefixed_pins_exactly_as_they_were(
    *, pinned_tag: str, release_tag: str, expected: bool
) -> None:
    """The regression witnesses, straight from the sweep log.

    `livespec-runtime` at `v0.11.0` read current and `livespec` at `v0.18.0` read
    stale under the old raw equality; both must keep those answers. The change is
    a pure WIDENING — it only adds same-version-different-text matches — so no
    unprefixed format can shift.
    """
    assert denotes_same_release(pinned_tag=pinned_tag, release_tag=release_tag) is expected


@pytest.mark.parametrize("pinned_tag", ["sha-deadbeef", "python-sha-deadbeef", "master", ""])
def test_denotes_same_release_rejects_a_pin_with_no_version_anchor(*, pinned_tag: str) -> None:
    """A pin whose version cannot be read must fail toward STALE, never toward fresh.

    Same direction `ordinal_distance` already takes for an absent tag: an
    unreadable pin surfaces for a human rather than disappearing from the scan.
    """
    assert denotes_same_release(pinned_tag=pinned_tag, release_tag="v0.51.4") is False


def test_denotes_same_release_still_matches_two_identical_versionless_tags() -> None:
    """The literal short-circuit is unconditional, so equal bytes are always current.

    This is what makes the change a widening rather than a replacement: nothing
    the old comparison accepted is newly rejected, whatever shape it had.
    """
    assert denotes_same_release(pinned_tag="master", release_tag="master") is True


def test_ordinal_distance_finds_a_layer_prefixed_pin_among_bare_release_tags() -> None:
    """The second half of the same defect.

    `gh release list` yields BARE tags, so a prefixed `current` matched nothing
    and silently took the `fallback` — which the caller passes as the staleness
    threshold itself. Every prefixed pin therefore reported maximally stale
    regardless of its true distance. At the default threshold of 1 that wrong
    answer coincides with the right one for a genuinely stale pin, which is why
    it hid behind the currency bug rather than showing up separately.
    """
    tags = ["v0.51.4", "v0.51.3", "v0.51.2", "v0.51.1"]

    assert ordinal_distance(tags=tags, current="python-v0.51.2", fallback=9) == 2


def test_ordinal_distance_is_zero_for_a_layer_prefixed_pin_at_the_latest_release() -> None:
    tags = ["v0.51.4", "v0.51.3"]

    assert ordinal_distance(tags=tags, current="python-rust-agent-v0.51.4", fallback=9) == 0


def test_ordinal_distance_does_not_report_a_tolerable_prefixed_pin_as_maximally_stale() -> None:
    """Why the `ordinal_distance` half had to be fixed too, not just the currency check.

    A consumer raising `staleness_threshold_releases` to 3 is asking to tolerate
    a two-release drift window. Under the fallback the prefixed pin returned 3 —
    tripping the very gate the threshold was raised to relax. It must return its
    true distance of 1.
    """
    tags = ["v0.51.4", "v0.51.3", "v0.51.2"]

    assert ordinal_distance(tags=tags, current="python-v0.51.3", fallback=3) == 1


def test_ordinal_distance_still_falls_back_for_a_versionless_pin() -> None:
    """Unchanged: an unreadable pin keeps reading as maximally stale."""
    tags = ["v0.51.4", "v0.51.3"]

    assert ordinal_distance(tags=tags, current="python-sha-deadbeef", fallback=7) == 7


def test_main_is_current_mode_prints_a_bare_true_for_a_prefixed_pin_at_the_latest(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The workflow pattern-matches this output, so it must be exactly one token.

    A two-valued token rather than an exit status: a crash in the module must not
    be indistinguishable from a "not current" verdict, which is the failure shape
    that hid the earlier `--ordinal-distance` defect.
    """
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--is-current", "python-v0.51.4", "v0.51.4"])

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["true"]


def test_main_is_current_mode_prints_a_bare_false_for_a_stale_pin(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--is-current", "python-v0.51.3", "v0.51.4"])

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["false"]


def test_main_is_current_mode_does_not_shadow_the_ordinal_distance_mode(
    *, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Adding a third argv mode must leave the existing two reachable."""
    monkeypatch.setattr("sys.stdin", io.StringIO("v0.51.4\nv0.51.3\n"))
    monkeypatch.setattr("sys.argv", ["pin_staleness", "--ordinal-distance", "v0.51.3", "1"])

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == ["1"]


# Acceptance criterion 3 — the prefix/version rule must have exactly ONE home.
#
# The defect was not that either half was wrong in isolation: it was that the
# REWRITE half (`fabro_image_pin_rewrite`) knew the tag grammar and the
# COMPARISON half did not. Any fix that re-derives the grammar — a second regex
# in this module, a bash prefix-strip in the workflow — recreates the same split
# and lets the halves drift apart again. These two tests fail if that happens.

_VERSION_ANCHOR_SOURCE = r"\d+\.\d+\.\d+"


def test_the_version_anchor_regex_has_exactly_one_definition_in_the_package() -> None:
    """Exactly one module may spell the semver anchor; every other consumes it.

    `fabro_image_pin_rewrite` owns it because it needs the match POSITION (to
    preserve the layer prefix), which is strictly more than extraction needs.
    `pin_staleness` consumes `tag_version_component` instead of writing its own.
    """
    definers = sorted(
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _PACKAGE_ROOT.rglob("*.py")
        if _VERSION_ANCHOR_SOURCE in path.read_text(encoding="utf-8")
    )

    assert definers == ["livespec_dev_tooling/cross_repo/fabro_image_pin_rewrite.py"], (
        "the tag version-anchor grammar must have exactly ONE definition; a second "
        f"copy is the defect this work-item fixed. Found it in: {definers}"
    )


def test_the_freshness_workflow_does_not_reimplement_the_grammar_in_bash() -> None:
    """No shell-side prefix-strip or version-extract may creep back into the scan.

    The tempting one-line fix — `${current##*-}` — would have worked on today's
    tags and become the second copy of the rule the moment the grammar changed.
    """
    workflow = _FRESHNESS_WORKFLOW_PATH.read_text(encoding="utf-8")

    forbidden = [
        fragment
        for fragment in ("${current##", "${current#", "${current%", "${latest##", "${latest#")
        if fragment in workflow
    ]

    assert forbidden == [], (
        "the freshness scan must delegate tag-grammar reasoning to `pin_staleness`, "
        f"not strip prefixes in shell. Found: {forbidden}"
    )


def test_the_freshness_workflow_uses_the_module_for_the_release_tag_currency_test() -> None:
    """The release-tag path must call `--is-current`, not compare raw tag bytes."""
    workflow = _FRESHNESS_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert '--is-current "$current" "$latest"' in workflow


def test_the_codex_acp_branch_keeps_its_raw_equality_comparison() -> None:
    """The codex-acp comparison is deliberately NOT the fleet-release comparison.

    It compares an npm package version from `npm view @zed-industries/codex-acp
    version` — not a fleet release tag — and its contract is "stale on ANY
    difference", with the ordinal staleness threshold explicitly not applying.
    Routing it through `denotes_same_release` would silently widen that contract,
    so this pins the raw equality in place.
    """
    workflow = _FRESHNESS_WORKFLOW_PATH.read_text(encoding="utf-8")
    _, _, after_npm_branch = workflow.partition('if [[ "$source" == "zed-industries/codex-acp" ]]')
    npm_branch, _, _ = after_npm_branch.partition("gh release view")

    assert 'if [[ "$current" == "$latest" ]]; then' in npm_branch
    assert "--is-current" not in npm_branch
