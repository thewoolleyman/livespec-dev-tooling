"""Record each expedited pull-request CI run on its incident work item.

An expedited pull-request CI run is a run of the incident CI job on a pull-request
head the independent controller has armed for an incident item. When its job
completes, the controller's signed `workflow_job` callback retains an unpublished
record (the run's key, the job's conclusion and any refusal code) in the protected
controller record, under the repository lock and without any network call. The
sweep then writes every retained record onto the incident item, outside the lock,
in the same marked-record family and through the same canonical ledger the
original-run evidence uses, so the item answers its runs without a forge read. A
record the item already carries is marked written and never written twice, so a
lost write or a restarted controller resumes from protected state.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_observer_arm,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import LeafCompletion
from livespec_dev_tooling._incident_original_run_canonical import LedgerPort
from livespec_dev_tooling._incident_pr_run_store import (
    add_record,
    mark_written,
    pending_records,
)
from livespec_dev_tooling.incident_observer_events import completion_run_attempt
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = [
    "INCIDENT_CI_JOB",
    "PR_RUN_MARKER",
    "PrRunCompletion",
    "PrRunSweep",
    "carried_digests",
    "record_text",
    "retain_callback_run",
    "retain_pr_run",
    "write_pending",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
PR_RUN_MARKER = "livespec-incident-pr-run-record-v1"
INCIDENT_CI_JOB = "incident-ci"
_INTERVAL_SECONDS = 300
_EXPECTED = (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError)


@dataclass(frozen=True, kw_only=True)
class PrRunCompletion:
    """One signature-verified completed job outside the target branch."""

    repository: str
    job_name: str
    head_sha: str
    run_id: int
    run_attempt: int
    conclusion: str


def retain_pr_run(*, state: Path, completion: PrRunCompletion) -> str:
    """Retain the unpublished record of an armed head's incident CI job; name what happened.

    `not-incident-ci` and `not-armed` retain nothing: a run on a head the controller has
    not armed is not an expedited pull-request CI run and receives no record.
    """
    if completion.job_name != INCIDENT_CI_JOB:
        return "not-incident-ci"
    with repository_lock(directory=state, repository=completion.repository) as path:
        record = load_record(path=path)
        arm = read_observer_arm(record=record)
        arm_id = record.get("observer_arm_id")
        if (
            arm is None
            or not isinstance(arm_id, str)
            or record.get("observer_arm_invalidated") is not None
            or arm.repository != completion.repository
            or arm.head_sha != completion.head_sha
        ):
            return "not-armed"
        key = {
            "repository": arm.repository,
            "incident_item_id": arm.incident_item_id,
            "attempt_id": arm.attempt_id,
            "generation": arm.generation,
            "arm_id": arm_id,
            "pr_number": arm.pr_number,
            "base_sha": arm.base_sha,
            "head_sha": arm.head_sha,
            "run_id": completion.run_id,
            "run_attempt": completion.run_attempt,
        }
        content = {"conclusion": completion.conclusion, "refusal": None}
        if not add_record(record=record, kind="unpublished", key=key, content=content):
            return "already-retained"
        save_record(path=path, record=record)
    return "retained"


def retain_callback_run(
    *, state: Path, completion: LeafCompletion, body: bytes, wake: Event
) -> str:
    """Retain a verified callback's run record and wake the sweep; name what happened."""
    attempt = completion_run_attempt(body=body)
    if attempt is None:
        return "run-attempt-unreadable"
    try:
        status = retain_pr_run(
            state=state,
            completion=PrRunCompletion(
                repository=completion.repository,
                job_name=completion.job_name,
                head_sha=completion.head_sha,
                run_id=completion.run_id,
                run_attempt=attempt,
                conclusion=completion.conclusion,
            ),
        )
    except (OSError, ValueError, TypeError, IncidentJsonRefusalError):
        return "state-unavailable"
    if status == "retained":
        wake.set()
    return status


def record_text(*, row: dict[str, Any]) -> str:
    """The marked comment that carries one record on the incident item."""
    body = {"kind": row["kind"], **row["key"], **row["content"], "digest": row["digest"]}
    return PR_RUN_MARKER + "\n" + json.dumps(body, sort_keys=True, separators=(",", ":"))


def carried_digests(*, ledger: LedgerPort, item_id: str) -> frozenset[str]:
    """The run-record digests the incident item already carries."""
    rows = cast("object", strict_json(text=ledger(["comments", item_id, "--json"]), limit=None))
    digests: set[str] = set()
    for row in cast("list[object]", rows) if isinstance(rows, list) else []:
        text = cast("dict[str, object]", row).get("text") if isinstance(row, dict) else None
        if not isinstance(text, str) or not text.startswith(PR_RUN_MARKER + "\n"):
            continue
        body = strict_json(text=text.removeprefix(PR_RUN_MARKER + "\n"), limit=None)
        digest = cast("dict[str, object]", body).get("digest") if isinstance(body, dict) else None
        if isinstance(digest, str):
            digests.add(digest)
    return frozenset(digests)


def write_pending(*, state: Path, repository: str, ledger: LedgerPort) -> tuple[str, ...]:
    """Write every retained record the item lacks; the digests now carried by the item."""
    with repository_lock(directory=state, repository=repository, existing_only=True) as path:
        owed = pending_records(record=load_record(path=path))
    carried: list[str] = []
    for row in owed:
        item_id = row["key"]["incident_item_id"]
        if row["digest"] not in carried_digests(ledger=ledger, item_id=item_id):
            _ = ledger(["comments", "add", item_id, record_text(row=row)])
        with repository_lock(directory=state, repository=repository) as path:
            record = load_record(path=path)
            if mark_written(record=record, digest=row["digest"]):
                save_record(path=path, record=record)
        carried.append(row["digest"])
    return tuple(carried)


@dataclass(frozen=True, kw_only=True)
class PrRunSweep:
    """The periodic, wakeable write of retained run records onto their items."""

    state: Path
    repository: str
    ledger: Callable[[], LedgerPort | None]
    interval_seconds: float = _INTERVAL_SECONDS
    wake: Event = field(default_factory=Event, compare=False, repr=False)
    crashed: Event = field(default_factory=Event, compare=False, repr=False)

    def sweep(self) -> tuple[str, ...]:
        """One pass; nothing is written while the tenant credential is unavailable."""
        ledger = self.ledger()
        if ledger is None:
            return ()
        return write_pending(state=self.state, repository=self.repository, ledger=ledger)

    def run(self, *, stop: Event) -> None:
        """Sweep at once, then on every wake or interval, until `stop` is set."""
        while not stop.is_set():
            try:
                _ = self.sweep()
            except (*_EXPECTED, IncidentJsonRefusalError) as error:
                _ = sys.stderr.write(f"incident-pr-run-sweep: {type(error).__name__}: {error}\n")
            _ = self.wake.wait(self.interval_seconds)
            self.wake.clear()

    def start(self, *, stop: Event, on_crash: Callable[[], None]) -> Thread:
        """Run the loop in a daemon thread; an unexpected crash calls `on_crash`."""
        thread = Thread(
            target=self._supervised, kwargs={"stop": stop, "on_crash": on_crash}, daemon=True
        )
        thread.start()
        return thread

    def _supervised(self, *, stop: Event, on_crash: Callable[[], None]) -> None:
        try:
            self.run(stop=stop)
        finally:
            if not stop.is_set():
                self.crashed.set()
                on_crash()
