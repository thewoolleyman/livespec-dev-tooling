"""Consume the canonical released reader process, never caller JSON authority."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.result import Result  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling._incident_observer_types import (  # noqa: E402
    ObserverArm,
    ObserverRegistration,
)
from livespec_dev_tooling.incident_authority_client import (  # noqa: E402
    AuthorityRefusal,
    call_authority,
)

__all__: list[str] = ["CurrentAuthorityReader"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@dataclass(frozen=True, kw_only=True)
class CurrentAuthorityReader:
    """The admission callback over the independently installed canonical reader.

    Host provisioning supplies the command prefix and verifies its released
    installation. Neither comes from a PR, webhook, environment incident payload
    or candidate checkout. An unavailable or unapproved reader refuses new
    admission; post-merge fulfillment of an existing arm does not call it again.
    """

    command: tuple[str, ...]
    repo: Path
    release: str
    installed_reader_approved: Callable[[str, tuple[str, ...]], bool]

    def __call__(self, subject: ObserverArm | ObserverRegistration) -> bool:
        if not self.command or not self.installed_reader_approved(self.release, self.command):
            return False
        flags = {
            "repo": str(self.repo),
            "repository": subject.repository,
            "item": subject.incident_item_id,
            "attempt": subject.attempt_id,
            "phase": subject.phase,
            "operation": subject.operation_id,
            "generation": str(subject.generation),
            "owner": subject.owner,
        }
        checked = call_authority(
            command=self.command, action="read-current", flags=flags, cwd=self.repo
        )
        attempt = _current_attempt(checked=checked)
        if attempt is None:
            return False
        expected = {
            "repository": subject.repository,
            "item_id": subject.incident_item_id,
            "attempt_id": subject.attempt_id,
            "phase": subject.phase,
            "operation_id": subject.operation_id,
            "generation": subject.generation,
            "owner": subject.owner,
        }
        if any(
            type(attempt.get(key)) is not type(value) or attempt.get(key) != value
            for key, value in expected.items()
        ):
            return False
        if (
            json.dumps(attempt, sort_keys=True, separators=(",", ":")).encode()
            != subject.authority_receipt
        ):
            return False
        if isinstance(subject, ObserverArm):
            return (attempt.get("pr_number"), attempt.get("base"), attempt.get("head")) == (
                subject.pr_number,
                subject.base_sha,
                subject.head_sha,
            )
        commits = attempt.get("landed_commits")
        return (
            isinstance(commits, list)
            and subject.head_sha in commits
            and attempt.get("head") == subject.candidate_revision
        )


def _current_attempt(
    *, checked: Result[dict[str, Any], AuthorityRefusal]
) -> dict[str, object] | None:
    if not is_successful(checked):
        return None
    result = checked.unwrap()
    attempt = result.get("attempt")
    if result.get("is_current") is not True or not isinstance(attempt, dict):
        return None
    return cast("dict[str, object]", attempt)
