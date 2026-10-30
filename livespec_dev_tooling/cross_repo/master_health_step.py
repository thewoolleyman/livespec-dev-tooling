"""Turn a recorded forge state into the ONE step a reconcile run takes.

Per `SPECIFICATION/contracts.md` section "Master-health reconciler",
and child D of plan `red-master-self-healing` (epic
`livespec-dev-tooling-zcp5vb`, work-item `livespec-dev-tooling-dw7dzd`).

THE SEAM `master_health_state` NAMES. That module's docstring records the split
this one serves: "the gathering lives in the reusable workflow" and the decision
is pure, so something must carry one to the other. This module is that carrier
and NOTHING else. It parses the recording, delegates every judgement to
`reconcile_step`, and writes the chosen step back out as JSON for the workflow
step that performs it. It decides nothing itself, which is why it can sit on the
network-touching side of the boundary without weakening the replayability the
pure modules exist for.

IT REACHES NO NETWORK, BY CONSTRUCTION AND BY TEST. Its name matches the
`master_health_*` glob that `tests/livespec_dev_tooling/cross_repo/
test_master_health_state.py` walks, so it inherits the same prohibition on
network, subprocess and model clients the sibling decision modules carry. That
is deliberate rather than incidental: a transport smuggled in here would become
a decision input no replay could reproduce. `argparse`, `json` and `pathlib` are
the whole of its machinery.

FAIL-CLOSED, AND LOUDLY. A recording this run cannot read or cannot parse exits
1 with a structlog diagnostic and writes NO step file, so the workflow's
`set -euo pipefail` reds the job. Defaulting to some step instead would have
this module making the one kind of judgement it exists not to make — and the
load-bearing instance is the malformed REVERT: read leniently as "no revert in
flight" it would send the decision table down the branch that OPENS one, for an
episode that already has a revert.

THE PAYLOAD IS PROJECTED OFF THE STEP'S OWN FIELDS, NOT ENUMERATED BY HAND, so
a field the decision core adds cannot reach the performing step as a silently
missing argument. This module was rebuilt once for exactly that reason: an
earlier cut was authored against the core's shapes of the day and went stale
under child C1's calibration slice (`livespec-dev-tooling-zdqnr2`), which added
`ReconcileConfig.gating_workflow` and `.unrelated_lookback_commits`, added
`MasterCommit.ci_workflow` and `.subject`, and dropped
`ReconcileState.unrelated_failure_signatures`. The PARSE side cannot be
projected the same way — a recording's keys are the forge's vocabulary, not the
dataclass's — so the sibling test enumerates `dataclasses.fields` and requires
each one, which is where that drift fails now.

THE NEEDS-ATTENTION TITLE CONVENTION IS HOMED HERE rather than in the workflow
YAML. The workflow hands over the TITLES of the open needs-attention issues it
found, and reads the title to write back off the step this module returns, so
"does this episode already have an issue?" and "what is a new one called?" are
answered by ONE implementation. A convention split across a shell script and a
Python module is a convention that drifts, and the symptom of that drift is a
second issue per episode — exactly what `episode_key` was keyed to prevent.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import cast

from livespec_dev_tooling.cross_repo._master_health_records import (
    number_field,
    parse_revert,
    positive_field,
    strings_field,
    text_field,
)
from livespec_dev_tooling.cross_repo.master_health_reconcile import (
    STEP_NEEDS_ATTENTION,
    ReconcileStep,
    reconcile_step,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    MasterCommit,
    ReconcileConfig,
    ReconcileState,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "NEEDS_ATTENTION_TITLE_PREFIX",
    "main",
    "needs_attention_title",
    "open_episode_keys",
    "step_payload",
]


# The title prefix the one-per-episode needs-attention issue carries, beside the
# fixed `NEEDS_ATTENTION_LABEL` the decision module owns. Both are JOINs with
# whatever reads the screen, so changing either silently empties that reader
# rather than erroring — the hazard `release_lane_issue` recorded first.
NEEDS_ATTENTION_TITLE_PREFIX = "master-health: "


def needs_attention_title(*, episode_key: str) -> str:
    """The title of the needs-attention issue for `episode_key`."""
    return f"{NEEDS_ATTENTION_TITLE_PREFIX}{episode_key}"


def open_episode_keys(*, titles: tuple[str, ...]) -> tuple[str, ...]:
    """The episode keys carried by `titles`, ignoring unrelated issues."""
    return tuple(
        title.removeprefix(NEEDS_ATTENTION_TITLE_PREFIX)
        for title in titles
        if title.startswith(NEEDS_ATTENTION_TITLE_PREFIX)
    )


def step_payload(*, step: ReconcileStep) -> dict[str, object]:
    """The chosen step as the JSON object the performing workflow step reads.

    Every field of the step travels, read off the dataclass rather than listed
    here — see this module's docstring for the drift that buys. The ONE derived
    key is the needs-attention title, which is this module's own convention and
    so has no field to project from.
    """
    payload: dict[str, object] = dict(asdict(step))
    payload["needs_attention_title"] = (
        needs_attention_title(episode_key=step.episode_key)
        if step.kind == STEP_NEEDS_ATTENTION and step.episode_key is not None
        else None
    )
    return payload


def _commit(*, payload: object) -> MasterCommit | None:
    """One recorded branch commit, or None when it does not parse.

    `ci_workflow` and `subject` are REQUIRED for the reason `MasterCommit`
    records: a record whose workflow is unrecorded would read as the gating
    one and let a non-gating failure start an episode, and a record whose
    subject is unrecorded would read as an ordinary merge — which is exactly
    what the release-commit and pin-bump rules route away from a plain revert.
    """
    if not isinstance(payload, dict):
        return None
    record = cast("dict[str, object]", payload)
    sha = text_field(record=record, key="sha")
    parent_sha = text_field(record=record, key="parent_sha")
    ci_workflow = text_field(record=record, key="ci_workflow")
    ci_conclusion = text_field(record=record, key="ci_conclusion")
    subject = text_field(record=record, key="subject")
    if sha is None or parent_sha is None or ci_workflow is None:
        return None
    if ci_conclusion is None or subject is None:
        return None
    return MasterCommit(
        sha=sha,
        parent_sha=parent_sha,
        # Legitimately absent on a direct push, which is the case the decision
        # table refuses to act on rather than hand-rolling a revert commit.
        pull_request=number_field(record=record, key="pull_request"),
        ci_workflow=ci_workflow,
        ci_conclusion=ci_conclusion,
        failure_signature=text_field(record=record, key="failure_signature"),
        subject=subject,
        # Legitimately absent: a run still in flight has not concluded. The hard
        # cap treats an unknown time as "cannot show the claim is inside it".
        ci_completed_at=number_field(record=record, key="ci_completed_at"),
        # Null when the forge did not report them; the revert guard refuses to
        # open a revert it cannot show is safe rather than assume no overlap.
        changed_paths=strings_field(record=record, key="changed_paths"),
    )


def _commits(*, payload: object) -> tuple[MasterCommit, ...] | None:
    """The recorded window, or None when ANY commit in it does not parse.

    All-or-nothing on purpose: a window silently short one commit is a window
    whose parent chain has a hole, and the culprit rule walks exactly that
    chain. It would reach a different answer rather than report a problem.
    """
    if not isinstance(payload, list):
        return None
    parsed: list[MasterCommit] = []
    for entry in cast("list[object]", payload):
        commit = _commit(payload=entry)
        if commit is None:
            return None
        parsed.append(commit)
    return tuple(parsed)


def _config(*, record: dict[str, object]) -> ReconcileConfig | None:
    """The committed-configuration half of the decision's inputs, or None.

    The first four fields are required and none is defaulted here. `gating_workflow`
    is a per-repository fact, and `unrelated_lookback_commits` is the bound that
    stops the already-failing read exonerating every regression — a default for
    either would be this module configuring the decision.

    The fix-forward fields are the opposite: a missing or malformed hard cap,
    stall duration or maintainer login does NOT refuse the recording. It parses
    to `None`, which the decision reads as "fail closed to revert-by-default" —
    every claim stops holding and only a green-CI revert is ever merged — so a
    bad value costs the fix-forward grace period and nothing else.
    """
    target_branch = text_field(record=record, key="target_branch")
    markers = strings_field(record=record, key="infra_outage_markers")
    gating_workflow = text_field(record=record, key="gating_workflow")
    lookback = number_field(record=record, key="unrelated_lookback_commits")
    if target_branch is None or markers is None:
        return None
    if gating_workflow is None or lookback is None:
        return None
    return ReconcileConfig(
        target_branch=target_branch,
        infra_outage_markers=markers,
        gating_workflow=gating_workflow,
        unrelated_lookback_commits=lookback,
        maintainer_login=text_field(record=record, key="maintainer_login"),
        hard_cap_minutes=positive_field(record=record, key="hard_cap_minutes"),
        stall_claim_to_fix_pr_minutes=positive_field(
            record=record, key="stall_claim_to_fix_pr_minutes"
        ),
        stall_ci_in_flight_minutes=positive_field(record=record, key="stall_ci_in_flight_minutes"),
        stall_fix_to_merge_minutes=positive_field(record=record, key="stall_fix_to_merge_minutes"),
        stall_merged_to_green_minutes=positive_field(
            record=record, key="stall_merged_to_green_minutes"
        ),
    )


def _state(*, record: dict[str, object]) -> ReconcileState | None:
    """The recorded forge-state half of the decision's inputs, or None."""
    head_sha = text_field(record=record, key="head_sha")
    rerun_outcome = text_field(record=record, key="rerun_outcome")
    commits = _commits(payload=record.get("commits"))
    titles = strings_field(record=record, key="needs_attention_issue_titles")
    if head_sha is None or rerun_outcome is None or commits is None or titles is None:
        return None
    revert_payload = record.get("revert_pull_request")
    revert = None if revert_payload is None else parse_revert(payload=revert_payload)
    if revert_payload is not None and revert is None:
        # See this module's docstring: a revert that will not parse must never
        # read as "no revert in flight".
        return None
    return ReconcileState(
        head_sha=head_sha,
        commits=commits,
        rerun_outcome=rerun_outcome,
        revert_pull_request=revert,
        open_needs_attention_episodes=open_episode_keys(titles=titles),
        observed_at=number_field(record=record, key="observed_at"),
    )


def _read_json_object(*, path: Path) -> dict[str, object] | None:
    """Read a JSON object from `path`; None on any read or parse failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return cast("dict[str, object]", payload)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m livespec_dev_tooling.cross_repo.master_health_step",
        description=(
            "Decide the ONE step that heals the recorded branch, reading the recorded "
            "forge state and committed configuration and writing the chosen step."
        ),
    )
    _ = parser.add_argument("--state", type=Path, required=True)
    _ = parser.add_argument("--step-out", type=Path, required=True)
    return parser


def main(*, argv: list[str] | None = None) -> int:
    """Decide one step from the recorded state; 1 and no step file on bad input."""
    log = structlog.get_logger("master_health_step")
    args = _build_parser().parse_args(argv)
    state_path = cast("Path", args.state)
    record = _read_json_object(path=state_path)
    if record is None:
        log.error(
            "recorded state unreadable or not a JSON object; wrote no step (fail-closed)",
            state=str(state_path),
        )
        return 1
    config = _config(record=record)
    state = _state(record=record)
    if config is None or state is None:
        log.error(
            "recorded state is malformed; wrote no step (fail-closed)",
            state=str(state_path),
            config_parsed=config is not None,
            state_parsed=state is not None,
        )
        return 1
    step = reconcile_step(state=state, config=config)
    _ = cast("Path", args.step_out).write_text(
        json.dumps(step_payload(step=step)) + "\n", encoding="utf-8"
    )
    log.info(
        "chose one reconcile step",
        kind=step.kind,
        reason=step.reason,
        episode_key=step.episode_key,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
