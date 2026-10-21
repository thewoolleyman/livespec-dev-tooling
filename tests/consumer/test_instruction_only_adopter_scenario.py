"""Consumer-tier: the `SPECIFICATION/scenarios.md` scenario in which the manifest reader
accepts an instruction-only adopter and holds it to plugin currency only.

    Given a `.livespec-fleet-manifest.jsonc` whose `adopters` array holds an entry
    with `profile` `["instruction-only"]` and `posture` `released`, and another with
    `profile` `["instruction-only"]` and `posture` `none`
    And the released adopter's repository carries no justfile, mise configuration or
    `.livespec.jsonc`, and its committed `.claude/settings.json` declares
    `livespecPluginCurrencySuccessor` with a non-empty `mechanism` and `documentedIn`
    When the manifest is parsed and the fleet-conformance sweep evaluates its adopters
    Then the parse MUST succeed, and the released adopter's adopter plugin-currency row
    MUST pass with no other row evaluated for it
    And the adopter with posture `none` MUST be reported posture-excluded without
    failing the sweep

    Given an adopter entry whose `profile` is <invalid>
    When the manifest is parsed
    Then the parse MUST fail with the `malformed-adopter` reason
    Examples of <invalid>: `["instruction-only", "baseline"]`;
    `["instruction-only", "orchestrator-plugin"]`; `["instructions-only"]`; the empty
    list

Every arm is driven over the shipped path the ADMIN world-gate lane drives — the
manifest TEXT (never a hand-built `Manifest`, so the reader under test is the one the
sweep really uses), the per-class obligation table, the injected `GhRunner` seam, the
member leg and the posture-gated adopter leg — with only the committed bytes varying
between arms.

WHY THE FIXTURE'S ADOPTER TREE CARRIES EXACTLY ONE FILE. The toolchain-less Given is
load-bearing rather than scenery. The adopter's tree lists `.claude/settings.json` and
nothing else, so a row other than the currency row that reached this repository would
find an absent justfile, an absent mise configuration and an absent `.livespec.jsonc`.
"No other row evaluated for it" is therefore asserted on two independent surfaces: the
gh reads that were MADE (a recording runner, so what the sweep did NOT read is
assertable) and the two legs' own accounting.

WHY A NONCONFORMANT CONTROL RIDES ALONG. "The row passes when the settings declare the
successor" is only an assertion about the row if the row can also fail: without the
control arm, a row that passed unconditionally — the vacuous green an unread `profile`
or an unreached leg produces — would satisfy it just as well.
"""

from __future__ import annotations

import json

import pytest
from returns.io import IOSuccess
from returns.result import Failure, Success

from livespec_dev_tooling.fleet._adopter_lane import (
    ADOPTER_CURRENCY_ROW_ID,
    POSTURE_EXCLUDED_EVENT,
    run_adopter_rows,
)
from livespec_dev_tooling.fleet._context import FleetContext, GhOutcome, GhResult
from livespec_dev_tooling.fleet._contract_rows import ADMIN_VANTAGE
from livespec_dev_tooling.fleet._lanes import run_member_rows
from livespec_dev_tooling.fleet.contract import Manifest, ManifestParseError, parse_manifest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_RELEASED = "acme-host"
_EXCLUDED = "acme-deploy"
_MEMBER = "widget"
_SETTINGS_PATH = ".claude/settings.json"

# The manifest the reader is handed: one ordinary fleet member, plus the two
# instruction-only adopters the scenario's Given names. `profile` is the one-element
# list livespec core v227 ratified; `posture` splits them.
_MANIFEST_SOURCE = json.dumps(
    {
        "owner": "acme",
        "fleet": [{"repo": _MEMBER, "class": "library"}],
        "adopters": [
            {"repo": _RELEASED, "profile": ["instruction-only"], "posture": "released"},
            {"repo": _EXCLUDED, "profile": ["instruction-only"], "posture": "none"},
        ],
    }
)

# The sanctioned successor slot, both fields non-empty — the shape a toolchain-less
# repository uses because it has no justfile to hang `ensure-plugins` off.
_SUCCESSOR_SETTINGS = json.dumps(
    {
        "livespecPluginCurrencySuccessor": {
            "mechanism": "inline SessionStart updater loop",
            "documentedIn": ".ai/plugin-currency.md",
        }
    }
)
# Settings satisfying NEITHER recognized currency form: no SessionStart
# ensure-plugins hook and no documented successor.
_NONCONFORMANT_SETTINGS = '{"hooks": {}}'

# The `profile` values the reader contract names malformed, verbatim from the
# scenario's `Examples of <invalid>` row.
_INVALID_PROFILES: tuple[list[str], ...] = (
    ["instruction-only", "baseline"],
    ["instruction-only", "orchestrator-plugin"],
    ["instructions-only"],
    [],
)

# The EXACT gh reads the adopter plugin-currency row makes against one repository: the
# repo metadata its canonical-ref resolution needs (memoized for the run, so it is read
# once however many paths follow), the tree listing at that ref, and the settings blob it
# found there. Any other read naming the adopter repo belongs to some other row, which is
# the violation — so this set is spelled out rather than loosely matched.
_CURRENCY_READS: frozenset[tuple[str, ...]] = frozenset(
    {
        ("api", f"repos/acme/{_RELEASED}"),
        ("api", f"repos/acme/{_RELEASED}/git/trees/master?recursive=1"),
        (
            "api",
            f"repos/acme/{_RELEASED}/contents/{_SETTINGS_PATH}?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        ),
    }
)


def _manifest() -> Manifest:
    """The parsed manifest, through the reader the sweep itself uses."""
    outcome = parse_manifest(source=_MANIFEST_SOURCE)
    assert isinstance(outcome, Success), (
        f"the Given's manifest MUST parse — a reader that refuses it is the "
        f"`malformed-adopter` red that made registering the toolchain-less "
        f"repositories a fleet-wide failure; got {outcome!r}"
    )
    return outcome.unwrap()


def _context(*, settings_text: str, calls: list[tuple[str, ...]]) -> FleetContext:
    """A canned-response context recording every gh invocation into `calls`.

    The released adopter's tree carries ONLY `.claude/settings.json`: no justfile, no
    mise configuration, no `.livespec.jsonc`, exactly as the Given states. Nothing at
    all is canned for the posture-excluded adopter, so a read of it would be visible
    both as a recorded call and as a skip.
    """
    tree = {"tree": [{"path": _SETTINGS_PATH, "mode": "100644"}], "truncated": False}
    table: dict[tuple[str, ...], GhResult] = {
        ("api", f"repos/acme/{_RELEASED}/git/trees/master?recursive=1"): GhResult(
            returncode=0, stdout=json.dumps(tree), stderr=""
        ),
        (
            "api",
            f"repos/acme/{_RELEASED}/contents/{_SETTINGS_PATH}?ref=master",
            "-H",
            "Accept: application/vnd.github.raw",
        ): GhResult(returncode=0, stdout=settings_text, stderr=""),
    }

    def run(*, args: list[str], stdin: str | None = None) -> GhOutcome:
        del stdin
        calls.append(tuple(args))
        return IOSuccess(table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="none")))

    return FleetContext(owner="acme", run_gh=run)


def _reads_naming_the_adopter(*, calls: list[tuple[str, ...]]) -> set[tuple[str, ...]]:
    """Every recorded gh call whose argv names the released adopter's repository."""
    return {call for call in calls if any(_RELEASED in arg for arg in call)}


class RecordingLog:
    """Logger double capturing each event's text AND its structured fields.

    A DOUBLE rather than a configured `structlog` logger, because the exclusion
    report is one of the things under test here: the scenario's "MUST be reported
    posture-excluded" is a claim about an emitted record, and a rendered line is
    not a surface a test can read the `posture` field back off. The shape mirrors
    the fleet suite's own `RecordingLog`.

    It carries `info` and `error` and NOT `warning`, which on this leg is the
    blind-row severity: none of this module's arms can produce a blind row (every
    one of them either reads the released adopter or excludes it by posture), and
    that path's coverage is the unit-tier adopter-lane suite's. Omitting the method
    is deliberate rather than an oversight — a double that cannot answer a call
    these arms never make raises instead of quietly absorbing a record nothing here
    asserts.
    """

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []

    def error(self, event: str, **kwargs: object) -> None:
        self.records.append((event, kwargs))

    def info(self, event: str, **kwargs: object) -> None:
        self.records.append((event, kwargs))

    def fields_for(self, *, event: str) -> list[dict[str, object]]:
        """The structured fields of every record whose event text is `event`."""
        return [fields for recorded, fields in self.records if recorded == event]


def test_a_released_instruction_only_adopter_is_held_to_plugin_currency_and_to_no_other_row() -> (
    None
):
    """One row, and it passes on the declared successor — proven by what was read."""
    calls: list[tuple[str, ...]] = []
    manifest = _manifest()
    log = RecordingLog()
    ctx = _context(settings_text=_SUCCESSOR_SETTINGS, calls=calls)

    assert manifest.adopters[0].profile == ("instruction-only",), (
        f"the parsed profile MUST be the single value `instruction-only` — it REPLACES "
        f"the `baseline` floor, so a profile carrying anything beside it is a different "
        f"claim about which obligations apply; got {manifest.adopters[0].profile!r}"
    )

    members = run_member_rows(
        ctx=ctx, manifest=manifest, log=log, vantages=frozenset({ADMIN_VANTAGE})
    )
    adopters = run_adopter_rows(ctx=ctx, manifest=manifest, log=log, vantage=ADMIN_VANTAGE)

    assert [verdict.member for verdict in members.member_verdicts] == [_MEMBER], (
        "an adopter is not a fleet member, so the per-class obligation table must never "
        "produce a verdict for one — a verdict here would mean the member rows had been "
        f"applied to a toolchain-less repository; got {members.member_verdicts!r}"
    )
    assert adopters.evaluated == 1, (
        f"the released adopter MUST be evaluated rather than skipped — a skip reads as "
        f"coverage while enforcing nothing; got {adopters!r}"
    )
    assert adopters.error_findings == 0, (
        f"a committed `.claude/settings.json` declaring `livespecPluginCurrencySuccessor` "
        f"with a non-empty `mechanism` and `documentedIn` satisfies the row; got "
        f"{adopters!r}"
    )
    assert adopters.blind_rows == 0, adopters
    assert _reads_naming_the_adopter(calls=calls) == _CURRENCY_READS, (
        "the ONLY reads naming the adopter must be the two the plugin-currency row "
        "makes: its repository carries no justfile, no mise configuration and no "
        "`.livespec.jsonc`, so any further read belongs to a row that must not have "
        f"been evaluated for it at all; got {sorted(_reads_naming_the_adopter(calls=calls))!r}"
    )


def test_the_currency_row_still_fails_a_released_adopter_that_declares_no_successor() -> None:
    """The control arm: the row CAN fail, so the pass above is earned, not vacuous."""
    calls: list[tuple[str, ...]] = []
    adopters = run_adopter_rows(
        ctx=_context(settings_text=_NONCONFORMANT_SETTINGS, calls=calls),
        manifest=_manifest(),
        log=RecordingLog(),
        vantage=ADMIN_VANTAGE,
    )

    assert adopters.evaluated == 1, adopters
    assert adopters.error_findings == 1, (
        "settings satisfying neither recognized currency form MUST fail the row — "
        "without this arm a row that passed unconditionally would satisfy the scenario "
        f"just as well; got {adopters!r}"
    )
    assert _reads_naming_the_adopter(calls=calls) == _CURRENCY_READS, calls


def test_an_instruction_only_adopter_whose_posture_is_none_is_posture_excluded() -> None:
    """Exclusion is reported, costs zero reads, and never fails the sweep."""
    calls: list[tuple[str, ...]] = []
    log = RecordingLog()

    adopters = run_adopter_rows(
        ctx=_context(settings_text=_SUCCESSOR_SETTINGS, calls=calls),
        manifest=_manifest(),
        log=log,
        vantage=ADMIN_VANTAGE,
    )
    excluded = [
        fields
        for fields in log.fields_for(event=POSTURE_EXCLUDED_EVENT)
        if fields["adopter"] == _EXCLUDED
    ]

    assert adopters.posture_excluded == (_EXCLUDED,), (
        f"a non-`released` posture is a declared choice the sweep NAMES rather than "
        f"implies, so the excluded adopter must appear in the leg's own accounting; got "
        f"{adopters!r}"
    )
    assert len(excluded) == 1, (
        f"the exclusion MUST be reported, not silent — an invisible exclusion is "
        f"indistinguishable from a repository the sweep forgot; got {log.records!r}"
    )
    assert excluded[0]["posture"] == "none", excluded
    assert excluded[0]["row"] == ADOPTER_CURRENCY_ROW_ID, excluded
    assert (
        adopters.error_findings == 0
    ), f"the sweep MUST NOT fail on a posture-excluded adopter; got {adopters!r}"
    assert adopters.blind_rows == 0, (
        f"an excluded adopter is never read, so it can never be the can't-read that "
        f"makes the row blind; got {adopters!r}"
    )
    assert not [call for call in calls if any(_EXCLUDED in arg for arg in call)], (
        "posture is honored by never reading the repository at all (the spec's "
        f"never-'helpfully'-updated rule), so zero reads may name it; got {calls!r}"
    )


def test_a_profile_that_is_not_exactly_instruction_only_rejects_the_whole_manifest() -> None:
    """Including the two combinations a membership reading of the rule would admit."""
    for profile in _INVALID_PROFILES:
        source = json.dumps(
            {
                "owner": "acme",
                "fleet": [{"repo": _MEMBER, "class": "library"}],
                "adopters": [
                    {"repo": _RELEASED, "profile": profile, "posture": "released"},
                ],
            }
        )
        outcome = parse_manifest(source=source)

        assert isinstance(outcome, Failure), (
            f"`instruction-only` REPLACES the `baseline` floor rather than adding to it, "
            f"so {profile!r} asks for a combination that does not exist and the whole "
            f"manifest must be refused — a document the sweep must not act on; got "
            f"{outcome!r}"
        )
        assert outcome.failure() == ManifestParseError(reason="malformed-adopter"), (
            f"the reason is what sends the operator to the offending record, and the "
            f"manifest is fetched from another repository, so a coarser cause leaves "
            f"them re-parsing it by hand; profile={profile!r} got {outcome.failure()!r}"
        )
