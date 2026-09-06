"""master_ci_green — master's head commit is green on the merge gate's own signal.

Guard Layer 1 mechanical check that prevents the silent-red-master
pattern: master CI failed three weeks ago, every PR merged onto red
master inherited the brokenness, no agent surfaced it. The check
ensures master CI is in a known-green state at every commit.

THE SIGNAL is the `ci-green` CHECK RUN on master's HEAD COMMIT, read
from `repos/{owner}/{repo}/commits/master/check-runs?check_name=ci-green`
— exactly what branch protection evaluates when it decides whether a
PR may land on master. It deliberately does NOT read the most recent
master CI WORKFLOW RUN's conclusion, which is a DIFFERENT signal that
disagrees with branch protection in three ways:

- A workflow run concludes `failure` when ANY of its jobs fails,
  including jobs that are not gates. `export-telemetry` is absent from
  `ci-green`'s `needs:` on purpose, so master can be perfectly
  mergeable while its newest run reads red — the shape observed on
  f1274d5 during the 2026-07-19 outage.
- A workflow run concludes `cancelled` when it is superseded or
  manually cancelled, while the head commit's required `ci-green`
  context stands at `success` from the run that did complete.
- `gh run list --branch master --limit 1` is not pinned to master's
  head commit at all: a re-run of an older commit is a newer run.

Reading the run conclusion therefore rejected work while master was
genuinely green (work-item livespec-dev-tooling-aa7, absorbing gam8 and
8o8e.22). A gate that guards merges must read what the merge gate reads.

External state: shells out to `gh api`. Five `gh` failure states are
kept apart, because four of them mean "this host was never able to
check at all" and one means "the check was attempted and returned no
answer":

- `gh` binary absent               -> exit 0 with a warning
- `gh` present, no credential      -> exit 0 with a warning
- `gh` credentialed, API returns 401 -> exit 0 with a warning
- `master` does not resolve on the remote -> exit 0 with a warning
- `gh` credentialed, API otherwise fails -> exit 1

The first four are the local-developer/environmental tolerance the
fail-soft exists for: someone who never installed `gh`, never
authenticated `gh`, whose locally-present credential is rejected, or
whose governed repo has no `master` branch at all cannot learn master's
CI state, and must not be blocked from running pre-commit. The fifth is
not that case, and folding it into the same branch is what made this
gate fail open.

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

Acceptable conclusions for the head commit's `ci-green` check run:
- "success"  → exit 0
- in-progress / queued → exit 0 with informational log (CI may
  not have caught up to a fresh master push yet)
- "failure" / "cancelled" / "timed_out" / "action_required" → exit 1
- no `ci-green` check run on the head commit → exit 0 with warning
  (a fresh repo, a repo that does not run the fan-in gate, or a push
  whose checks have not been created yet)

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


class _CiGreenCheckRun(TypedDict, total=False):
    """Shape of one check-run record from the commit check-runs endpoint.

    `total=False` mirrors the defensive `.get(...)` access — both keys are
    optional, so the typed boundary matches runtime semantics exactly (no
    behavior change vs. the prior `object`/`Any` annotations).
    """

    status: str
    conclusion: str


# The branch whose head commit is read. This gate is `master_ci_green`; a
# governed repo whose default branch is `main` has no `master` commit, and
# GitHub answers with `_NO_COMMIT_MARKER`, routing it to the environmental
# skip below rather than to a hard failure.
_MASTER_REF = "master"
# The single required context branch protection enforces fleet-wide: the
# fan-in gate job that `needs:` every check-bearing job. One stable name
# gates the whole matrix and never churns as checks are added.
_REQUIRED_CHECK_NAME = "ci-green"
# `{owner}`/`{repo}` are `gh api` placeholders, expanded by `gh` from the
# current directory's repository, so the endpoint stays correct in every
# governed sibling repo without a hardcoded owner/repo.
_CHECK_RUNS_ENDPOINT = (
    f"repos/{{owner}}/{{repo}}/commits/{_MASTER_REF}"
    f"/check-runs?check_name={_REQUIRED_CHECK_NAME}"
)
# GitHub's commit-scoped endpoints answer with this EXACT message body when
# the ref does not resolve to a commit. It is the definitive "this repo has
# no such branch" disambiguator, in the same spirit as
# `branch_protection_alignment`'s "Branch not protected" marker — and it is
# NOT an outage signature, so classifying it as an environmental skip does
# not reopen the hole the credentialed-failure branch closes.
_NO_COMMIT_MARKER = "No commit found for SHA"
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


def _classify_failed_gh_call(
    *,
    log: structlog.stdlib.BoundLogger,
    stdout_full: str,
    stderr_full: str,
) -> Literal["skip", "unprovable"]:
    """Classify a failed `gh api` call after it returns non-zero.

    The missing-ref marker is looked for across BOTH streams because `gh`
    writes the API's JSON error body to stdout and its own one-line
    rendering of the same message to stderr; either alone is enough, and
    reading both keeps the classification stable if that split changes.
    """
    stderr = stderr_full.strip()[:200]
    if _NO_COMMIT_MARKER in f"{stdout_full}\n{stderr_full}":
        log.warning(
            "master ref does not resolve on the remote; skipping master-CI-green check",
            stderr=stderr,
            hint=(
                "this repo has no `master` branch, so there is no master CI "
                "state to read on this host"
            ),
        )
        return "skip"
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


def _fetch_master_ci_green_check(
    *,
    log: structlog.stdlib.BoundLogger,
) -> tuple[str | None, str | None] | Literal["skip", "unprovable"]:
    """Return (status, conclusion) for master's head-commit `ci-green`, or an outcome.

    On API success, returns the pair (`status`, `conclusion`) of the
    `ci-green` CHECK RUN on master's head commit — the signal branch
    protection evaluates. `conclusion` is None until the check completes.

    Returns the literal `"skip"` when this host was never able to check —
    no `gh` binary, no stored credential, invalid credential, no `master`
    ref, or no `ci-green` check run on master's head commit — which the
    caller treats as a non-blocking pass.

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
        ["gh", "api", _CHECK_RUNS_ENDPOINT],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return _classify_failed_gh_call(
            log=log,
            stdout_full=completed.stdout,
            stderr_full=completed.stderr,
        )
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        log.error("unexpected gh response shape", payload_type=type(parsed).__name__)
        return "skip"
    # The `cast` is the single typed parse boundary: `json.loads` yields
    # `Any`, and the `isinstance` guard narrows to a `dict`. Members are
    # typed as `object` so the `isinstance` shape checks below stay
    # load-bearing runtime guards against a malformed `gh` payload; the
    # inner cast then types `.get(...)` access.
    payload = cast("dict[str, object]", parsed)
    check_runs = payload.get("check_runs")
    if not isinstance(check_runs, list) or not check_runs:
        log.warning(
            "no ci-green check run on master's head commit; skipping master-CI-green check",
            hint=(
                "run the ci-green fan-in gate on master to populate the signal "
                "branch protection reads"
            ),
        )
        return "skip"
    first = cast("list[object]", check_runs)[0]
    if not isinstance(first, dict):
        log.error("unexpected ci-green check-run shape", payload_type=type(first).__name__)
        return "skip"
    run = cast("_CiGreenCheckRun", first)
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
    fetched = _fetch_master_ci_green_check(log=log)
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
            "master CI is red on its head commit's ci-green check",
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
