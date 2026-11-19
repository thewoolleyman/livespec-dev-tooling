"""Publish ci-green's informational master-health check run.

The aggregate ``ci-green`` status remains the required merge gate.  This
publisher records the separate, non-required explanation of that status so a
reader can distinguish a defect from a fully evidenced external failure.
"""

# ruff: noqa: PLR0913

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, cast

__all__: list[str] = ["publish_master_health"]

_SUCCESSFUL_RESULTS = frozenset({"success", "skipped"})
_NON_CARRIER_CONCLUSIONS = frozenset({"cancelled", "skipped", "in_progress"})
_MAX_MASTER_HEALTH_READS = 2
_EXTERNAL_EPISODE_LIMIT = timedelta(hours=24)
_EXTERNAL_RED_LABEL = "master-green-external-red"
_UNREADABLE_EPISODE_TITLE = "master-green: episode unreadable"


def _publication_time() -> datetime:
    """Return the UTC instant at which ci-green publishes master-health."""
    return datetime.now(tz=timezone.utc)


def _episode_expired(*, episode: Mapping[str, Any]) -> bool:
    """Whether a readable episode has exceeded the external-red tolerance."""
    started_at = episode.get("started_at")
    if not isinstance(started_at, str):
        return False
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if started.tzinfo is None:
        return False
    return _publication_time() - started.astimezone(timezone.utc) > _EXTERNAL_EPISODE_LIMIT


def _open_issues(*, forge: Any, **query: str) -> list[Mapping[str, Any]]:
    """Return open alert issues when this forge supports the alert seam."""
    find_open_issues = getattr(forge, "find_open_issues", None)
    if not callable(find_open_issues):
        return []
    issues: object = find_open_issues(**query)
    if not isinstance(issues, Sequence):
        return []
    values = cast(Sequence[object], issues)
    return [issue for value in values if (issue := _as_mapping(value=value)) is not None]


def _create_alert_issue(*, forge: Any, title: str) -> None:
    """Create an alert only through a forge that exposes the issue seam."""
    create_issue = getattr(forge, "create_issue", None)
    if callable(create_issue):
        _ = create_issue(title=title, labels=[_EXTERNAL_RED_LABEL])


def _raise_one_alert(*, forge: Any, title: str) -> None:
    """Raise the one open issue for an alert title, including a race re-read."""
    if _open_issues(forge=forge, title=title):
        return
    _create_alert_issue(forge=forge, title=title)
    _ = _open_issues(forge=forge, title=title)


def _close_open_alerts(*, forge: Any) -> None:
    """Close every external-red alert once a green master ends the episode."""
    close_issue = getattr(forge, "close_issue", None)
    if not callable(close_issue):
        return
    for issue in _open_issues(forge=forge, label=_EXTERNAL_RED_LABEL):
        _ = close_issue(
            issue=issue,
            comment="Closing because master-health is green.",
        )


def _alert_for_summary(
    *,
    forge: Any,
    verdict: str,
    episode: Mapping[str, Any] | None,
    expired: bool,
) -> None:
    """Reconcile the issue signal that accompanies a master-health summary."""
    if verdict == "green":
        _close_open_alerts(forge=forge)
        return
    if episode is None and verdict in {"external", "defect"}:
        _raise_one_alert(forge=forge, title=_UNREADABLE_EPISODE_TITLE)
        return
    if verdict != "external" or not expired or episode is None:
        return
    earliest_run_id = episode.get("earliest_run_id")
    if isinstance(earliest_run_id, int):
        _raise_one_alert(
            forge=forge,
            title=f"master-green: external episode {earliest_run_id}",
        )


def _as_mapping(*, value: object) -> Mapping[str, Any] | None:
    """Narrow forge JSON to the mapping shape the clock consumes."""
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, Any], value)


def _episode_from_master_health(*, record: object) -> dict[str, Any] | None:
    """Return the episode carried by one prior master-health record."""
    parsed_record = _as_mapping(value=record)
    if parsed_record is None:
        return None
    episode = _as_mapping(value=parsed_record.get("episode"))
    return dict(episode) if isinstance(episode, Mapping) else None


def _run_is_non_carrier(*, run: Mapping[str, Any]) -> bool:
    """Whether a workflow run cannot carry an episode forward."""
    conclusion = run.get("conclusion")
    return (
        conclusion is None
        or conclusion in _NON_CARRIER_CONCLUSIONS
        or run.get("status") == "in_progress"
    )


def _new_episode(*, run: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build an episode anchored at a completed non-success workflow run."""
    run_id = run.get("id")
    completed_at = run.get("completed_at")
    if not isinstance(run_id, int) or not isinstance(completed_at, str):
        return None
    return {"earliest_run_id": run_id, "started_at": completed_at}


def _is_rerun(*, run: Mapping[str, Any]) -> bool:
    """GitHub exposes the first execution as attempt one."""
    attempt = run.get("run_attempt")
    return isinstance(attempt, int) and attempt > 1


def _run_id(*, run: Mapping[str, Any]) -> int | None:
    """Return a forge run identifier only when it can be read safely."""
    identifier = run.get("id")
    return identifier if isinstance(identifier, int) else None


def _recent_master_push_runs(*, forge: Any) -> list[Mapping[str, Any]]:
    """Read and normalize the publisher's single recent-runs response."""
    list_runs = getattr(forge, "list_master_push_runs", None)
    if not callable(list_runs):
        return []
    response: object = list_runs()
    if not isinstance(response, Sequence):
        return []
    values = cast(Sequence[object], response)
    return [run for value in values if (run := _as_mapping(value=value)) is not None]


def _episode_before_current(
    *,
    forge: Any,
    prior_runs: Sequence[Mapping[str, Any]],
    episode_runs: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Walk older runs until a carrier, a success, or the bounded miss limit."""
    non_carriers = 0
    for prior_run in prior_runs:
        if _run_is_non_carrier(run=prior_run):
            continue
        if prior_run.get("conclusion") == "success":
            return _new_episode(run=episode_runs[-1]) if episode_runs else None

        prior_run_id = _run_id(run=prior_run)
        record: object = (
            forge.read_master_health(prior_run_id) if prior_run_id is not None else None
        )
        carried = _episode_from_master_health(record=record)
        if carried is not None:
            return carried
        non_carriers += 1
        if non_carriers >= _MAX_MASTER_HEALTH_READS:
            return None
        episode_runs.append(prior_run)

    return None


def _derive_episode(*, forge: Any, run_id: int) -> dict[str, Any] | None:
    """Derive one open episode with one runs read and at most two check reads.

    The workflow-runs response is newest first.  Only completed, non-success
    runs can carry an episode; cancelled, skipped and unfinished entries are
    intentionally transparent.  A success ends the search and identifies the
    oldest failure in the new episode.
    """
    runs = _recent_master_push_runs(forge=forge)
    current_index = next(
        (index for index, run in enumerate(runs) if run.get("id") == run_id),
        None,
    )
    if current_index is None:
        return None

    current_run = runs[current_index]
    if _is_rerun(run=current_run):
        earlier_master_health: object = forge.read_master_health(run_id)
        return _episode_from_master_health(record=earlier_master_health)

    episode_runs = [] if _run_is_non_carrier(run=current_run) else [current_run]
    return _episode_before_current(
        forge=forge,
        prior_runs=runs[current_index + 1 :],
        episode_runs=episode_runs,
    )


def publish_master_health(
    *,
    forge: Any,
    head_sha: str,
    run_id: int,
    ci_green_passed: bool,
    jobs: Sequence[Mapping[str, Any]],
    episode: Mapping[str, Any] | None = None,
    expired: bool = False,
) -> dict[str, Any]:
    """Publish one completed ``master-health`` run and return its summary.

    ``external`` is deliberately unavailable when ci-green's own reads failed:
    an aggregate which did not establish its inputs is a defect even if every
    reported gating job appears green.
    """
    failed_jobs = [job for job in jobs if job.get("result") not in _SUCCESSFUL_RESULTS]
    verdict = (
        "green"
        if ci_green_passed and not failed_jobs
        else "external"
        if ci_green_passed and all(bool(job.get("external_only")) for job in failed_jobs)
        else "defect"
    )
    if verdict != "green" and episode is None:
        episode = _derive_episode(forge=forge, run_id=run_id)
    expired = bool(expired or (episode is not None and _episode_expired(episode=episode)))
    summary: dict[str, Any] = {
        "verdict": verdict,
        "head_sha": head_sha,
        "run_id": run_id,
        "episode": None if verdict == "green" else episode,
        "expired": False if verdict == "green" else expired,
        "jobs": [
            {
                "name": job.get("name"),
                "external_only": bool(job.get("external_only")),
                "defect_findings": job.get("defect_findings", 0),
                "records": job.get("records", []),
            }
            for job in jobs
        ],
    }
    forge.create_check_run(
        name="master-health",
        head_sha=head_sha,
        status="completed",
        conclusion="success" if verdict == "green" else "neutral",
        output={
            "title": f"master-health: {verdict}",
            "summary": json.dumps(summary, separators=(",", ":"), sort_keys=True),
        },
    )
    _alert_for_summary(
        forge=forge,
        verdict=verdict,
        episode=summary["episode"],
        expired=bool(summary["expired"]),
    )
    return summary
