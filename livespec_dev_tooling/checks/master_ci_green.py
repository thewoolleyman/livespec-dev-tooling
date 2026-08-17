"""master_ci_green — master branch's most recent CI run is green.

Guard Layer 1 mechanical check that prevents the silent-red-master
pattern: master CI failed three weeks ago, every PR merged onto red
master inherited the brokenness, no agent surfaced it. The check
ensures master CI is in a known-green state at every commit.

External state: shells out to `gh run list` to fetch the most recent
master CI run's conclusion. Four `gh` failure states are kept apart,
because three of them mean "this host was never able to check at all"
and one means "the check was attempted and returned no answer":

- `gh` binary absent               -> exit 0 with a warning
- `gh` present, no credential      -> exit 0 with a warning
- `gh` credentialed, API returns 401 -> exit 0 with a warning
- `gh` credentialed, API otherwise fails -> exit 1

The first three are the local-developer/environmental tolerance the
fail-soft exists for: someone who never installed `gh`, never
authenticated `gh`, or whose locally-present credential is rejected
cannot learn master's CI state, and must not be blocked from running
pre-commit. The fourth is not that case, and folding it into the same
branch is what made this gate fail open.

That fold rested on the premise "CI sets GH_TOKEN so the call always
succeeds there", which is false twice over. This check is one of the
two world gates deliberately EXCLUDED from the CI matrix (see the
world-gate exclusion comment in `.github/workflows/ci.yml`); it
enforces at pre-push instead, so "running in CI" is not a state it is
ever in. And an authenticated call still returns HTTP 503 when GitHub
is down. During the 2026-07-19 GitHub outage this check therefore
logged a warning and exited 0 while master was genuinely red — the
precise silent-red-master hole it exists to close. A caller that could
have checked and got no answer has not proven master is green, so it
does not pass.

Credential presence is probed with `gh auth token`, deliberately not
`gh auth status`: the token probe reads only local state and makes no
network call, so an outage cannot flip a credentialed caller onto the
fail-soft path and reopen the hole. That means the probe proves
presence, not validity: a present but expired/revoked/insufficiently
scoped credential can still be rejected by the API. Exactly HTTP 401 is
classified with the no-credential environmental branch because that
caller also could not check master's CI state at all; HTTP 5xx and any
other credentialed failure remain hard failures. The auth subprocess's
stdout is the token itself; only its return code is ever read, and it is
never logged.

There is deliberately NO env lever, flag, or severity knob softening
any of the above (wontfix li-4x3a45, broadened by maintainer directive
2026-07-04; see livespec `.ai/ci-gate-discipline.md`). The remedy for
a red or unprovable master is to fix or revert what reddened it, or to
wait for the API to come back — never to bypass the gate.

Acceptable conclusions:
- "success"  → exit 0
- in-progress / queued → exit 0 with informational log (CI may
  not have caught up to a fresh master push yet)
- "failure" / "cancelled" / "timed_out" / "action_required" → exit 1
- empty list (no CI runs ever) → exit 0 with warning (probably a
  fresh repo)

Output discipline matches sibling checks: structlog JSON to stderr;
no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal, TypedDict, cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402

__all__: list[str] = []


class _CiRun(TypedDict, total=False):
    """Shape of one `gh run list --json status,conclusion` record.

    `total=False` mirrors the defensive `.get(...)` access — both keys are
    optional, so the typed boundary matches runtime semantics exactly (no
    behavior change vs. the prior `object`/`Any` annotations).
    """

    status: str
    conclusion: str


_GREEN_CONCLUSIONS: frozenset[str] = frozenset({"success"})
_PENDING_STATUSES: frozenset[str] = frozenset(
    {"queued", "in_progress", "waiting", "pending", "requested"},
)
_RED_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "cancelled", "timed_out", "action_required", "stale", "startup_failure"},
)


def _gh_has_stored_credential() -> bool:
    """Return True when `gh` holds a credential for the current host.

    Probes `gh auth token`, which resolves the credential from the
    environment (`GH_TOKEN` / `GITHUB_TOKEN`) or the local keyring /
    `hosts.yml` and makes NO network call. That offline property is the
    whole point: `gh auth status` validates against the API and would
    report failure during an outage, which would route a credentialed
    caller onto the fail-soft path and reopen the hole this split closes.

    The subprocess's stdout is the token itself. Only `returncode` is
    read; stdout and stderr are captured solely to keep them off the
    terminal, and neither is logged.
    """
    completed = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _gh_failed_due_to_invalid_credential(*, stderr: str) -> bool:
    """Return True when `gh` reports an HTTP 401 credential rejection."""
    return "HTTP 401" in stderr


def _classify_failed_gh_run(
    *,
    log: structlog.stdlib.BoundLogger,
    stderr_full: str,
) -> Literal["skip", "unprovable"]:
    """Classify a failed `gh run list` after the API call returns non-zero."""
    stderr = stderr_full.strip()[:200]
    if not _gh_has_stored_credential():
        log.warning(
            "gh CLI has no stored credential; skipping master-CI-green check",
            stderr=stderr,
            hint="run `gh auth login` (or set GH_TOKEN) to arm the master-CI-green gate",
        )
        return "skip"
    if _gh_failed_due_to_invalid_credential(stderr=stderr_full):
        log.warning(
            "gh credential was rejected; skipping master-CI-green check",
            stderr=stderr,
            hint=(
                "refresh the gh credential; HTTP 401 means this host could not "
                "check master CI state"
            ),
        )
        return "skip"
    log.error(
        "gh api call failed while credentialed; cannot prove master CI is green",
        stderr=stderr,
        hint=(
            "GitHub API error or outage - master CI state is unknown; "
            "retry once the GitHub API is reachable"
        ),
    )
    return "unprovable"


def _fetch_latest_master_ci(
    *,
    log: structlog.stdlib.BoundLogger,
) -> tuple[str | None, str | None] | Literal["skip", "unprovable"]:
    """Return (status, conclusion) for the latest master CI run, or an outcome.

    On API success, returns the pair (`status`, `conclusion`);
    `conclusion` is None until the run completes.

    Returns the literal `"skip"` when this host was never able to check —
    no `gh` binary, no stored credential, invalid credential, or no CI runs
    on master yet — which the caller treats as a non-blocking pass.

    Returns the literal `"unprovable"` when a credentialed `gh` attempted
    the call and it failed. That is NOT a skip: the gate was armed, it ran,
    and it did not come back with a green master, so the caller fails.
    """
    if shutil.which("gh") is None:
        log.warning(
            "gh CLI not on PATH; skipping master-CI-green check",
            hint="install the gh CLI to arm the master-CI-green gate on this host",
        )
        return "skip"
    completed = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--branch",
            "master",
            "--limit",
            "1",
            "--workflow",
            "CI",
            "--json",
            "status,conclusion",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return _classify_failed_gh_run(
            log=log,
            stderr_full=completed.stderr,
        )
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, list) or not parsed:
        log.warning(
            "no CI runs on master yet; skipping master-CI-green check",
            hint="run CI on master to populate signal",
        )
        return "skip"
    # The `cast` is the single typed parse boundary: `json.loads` yields
    # `Any`, and the `isinstance` guard narrows to a non-empty `list`. The
    # elements are cast to `object` so the per-element `isinstance(first,
    # dict)` shape check below stays a load-bearing runtime guard against a
    # malformed `gh` payload; the inner cast then types `.get(...)` access.
    payload = cast("list[object]", parsed)
    first = payload[0]
    if not isinstance(first, dict):
        log.error("unexpected gh response shape", payload_type=type(first).__name__)
        return "skip"
    run = cast("_CiRun", first)
    status_raw = run.get("status")
    conclusion_raw = run.get("conclusion")
    status = status_raw if isinstance(status_raw, str) else None
    conclusion = conclusion_raw if isinstance(conclusion_raw, str) else None
    return (status, conclusion)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("check_master_ci_green")
    fetched = _fetch_latest_master_ci(log=log)
    # `isinstance(..., str)` is the narrowing form: it splits the outcome
    # literals off the (status, conclusion) tuple so the unpacking below is
    # type-safe, and it keeps "unprovable" a hard failure rather than
    # collapsing back into the skip path the outage exploited.
    if isinstance(fetched, str):
        if fetched == "unprovable":
            return 1
        return 0
    status, conclusion = fetched
    if status in _PENDING_STATUSES:
        log.info(
            "master CI is still pending; treating as non-blocking",
            status=status,
            conclusion=conclusion,
        )
        return 0
    if conclusion in _GREEN_CONCLUSIONS:
        return 0
    if conclusion in _RED_CONCLUSIONS:
        log.error(
            "master CI is red on its most recent run",
            status=status,
            conclusion=conclusion,
            hint="fix master before landing new work",
        )
        return 1
    log.warning(
        "master CI returned an unrecognized conclusion; treating as non-blocking",
        status=status,
        conclusion=conclusion,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
