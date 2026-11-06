"""Consume the canonical released reader process, never caller JSON authority."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_types import ObserverArm, ObserverRegistration

__all__: list[str] = ["CurrentAuthorityReader"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# The reader ceiling. One read-current pass over a fenced generation-2 chain
# makes seven bd calls and measured 7.4 s at load average 12, 9.2 s at load 16
# and a kill at 10.16 s at load 20 on the dev host (livespec-dev-tooling-ws2idp,
# 2026-11-06), so 10 s refused a current, verified chain. The CI client's
# ceiling in incident_ci_authority is longer than this plus the observer's own
# overhead, so a job read outwaits the reader rather than racing it.
_READER_TIMEOUT_SECONDS = 45


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
        argv = [
            *self.command,
            "read-current",
            *[part for name, value in flags.items() for part in ("--" + name, value)],
        ]
        reply = _read_reply(argv=argv, cwd=self.repo)
        attempt = _current_attempt(reply=reply)
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


def _read_reply(*, argv: list[str], cwd: Path) -> object:
    try:
        result = subprocess.run(  # noqa: S603 -- approved installed reader argv; no shell or request command.
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_READER_TIMEOUT_SECONDS,
            check=False,
        )
        return json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def _current_attempt(*, reply: object) -> dict[str, object] | None:
    if not isinstance(reply, dict):
        return None
    reply = cast("dict[str, object]", reply)
    if type(reply.get("schema")) is not int or reply.get("schema") != 1:
        return None
    if reply.get("status") != "verified" or reply.get("authorizes_current_effects") is not True:
        return None
    result = reply.get("result")
    if not isinstance(result, dict):
        return None
    result = cast("dict[str, object]", result)
    attempt = result.get("attempt")
    if result.get("is_current") is not True or not isinstance(attempt, dict):
        return None
    return cast("dict[str, object]", attempt)
