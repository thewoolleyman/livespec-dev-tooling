"""check_authority — the check-set members a delegated gate Job must NOT run.

The "What the delegated gate runs" bullet of this repository's own
`SPECIFICATION/contracts.md`, in its delegated pre-push gate section, ratified
v082. A delegated gate submits a Job that runs the gated repository's own check
recipe against the committed tree, and that Job is handed NO AUTHORITY: it holds
no work-items-ledger credential and no admin-scoped forge token, by design. So a
member that reads an AUTHORIZATION held outside the tree — a maintainer approval
label on a work item, the forge's repository administration settings — cannot
answer there at all, and a check that cannot reach a credential it needs FAILS
inside a gate Job where the local fall-through would only warn.

MEASURED, TWICE, ON CORRECT TREES. On 2026-10-19 an authorized change to a CI
workflow file, carrying its `approval:workflow-edit` label, failed gate Job
`gate-livespec-dev-tooling-54f19942138d` with `check-no-workflow-edits: the
ledger-held authorization could not be evaluated -- FAILING CLOSED`, because the
pod holds no `bd` and no ledger credential. livespec's first delegated run failed
`check-branch-protection-alignment` the same way, on an HTTP 403 against the gate
forge credential. Both verdicts were right about the POD and wrong about the
TREE, and neither may be fixed by handing the Job a credential: the authority a
member reads stays with the host that already holds it, which is why this module
answers "which members leave the Job" rather than "which credential to add".

WHERE A DECLARATION LIVES, and why the shape mirrors `check_purity`'s. A member
that exists only in one repository declares its authority as an
`# authority: <value>` annotation on its `check-targets.txt` line, read
STATICALLY so resolving a check set costs one file read on the pre-push path.
The annotation sits beside that line's purity annotation and is invisible to the
inventory's other reader: `scripts/just/check.sh` strips every `#`-comment from
the file before mirroring it against the justfile's literal array.

ABSENCE MEANS "RUNS IN THE JOB", which is the OPPOSITE default from purity's and
deliberately so. There, absence of evidence must never be read as evidence of
purity, because that error memoizes an impure verdict. Here the default keeps the
Job's coverage: an undeclared member runs on the cluster, where the whole
aggregate runs, rather than being quietly moved onto the pushing host where only
the authority members are meant to run. A member that genuinely needs the host's
own credentials says so, in one line, where the member is declared.

A DECLARATION NAMING NEITHER AUTHORITY REACHES THE FAILURE TRACK rather than
folding into that default, for `check_purity`'s reason: a typo is a registry bug,
and "I cannot read this" must not be spelled the same way as "this member needs
no authority" — the second would hand a ledger-reading member back to a pod that
cannot answer for it, which is the state this module exists to end.

CLI:
    python -m livespec_dev_tooling.check_authority members
        Print, one per line, the members of THIS repository's own check
        inventory that declare they read an authorization held outside the
        tree — the set a delegated gate Job must not run, in inventory order.
        Exit 1, having printed nothing, when a declaration cannot be read.

Output discipline: the `members` subcommand writes its one-name-per-line report
to stdout, which is why this file is declared in this repository's
`supervisor_entry_files`. Diagnostics stay on stderr as structlog JSON.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — same.
from returns.pipeline import is_successful  # noqa: E402  — same.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — same.

__all__: list[str] = []

# The two authorities the ratified bullet names: the work-items ledger (for
# example a maintainer approval label) and the forge's repository administration
# settings. A CLOSED vocabulary rather than a free-text reason, so a member
# cannot leave the gate Job on a declaration nothing can act on.
LEDGER = "ledger"
FORGE_ADMIN = "forge-admin"

_AUTHORITIES = frozenset({LEDGER, FORGE_ADMIN})

_INVENTORY_NAME = "check-targets.txt"
_SLUG_PREFIX = "check-"
_MEMBERS = "members"

# A repo-private member's declaration: a trailing `# authority: <value>` comment
# on its inventory line, beside the `# purity:` annotation that is already there.
_INVENTORY_DECLARATION = re.compile(r"#\s*authority:\s*(?P<value>\S+)")

_MALFORMED_REASON = (
    f"an authority declaration must be the string {LEDGER!r} or {FORGE_ADMIN!r}; a value "
    f"outside that vocabulary cannot be acted on, and treating it as 'no authority' would "
    f"spell a registry bug exactly like a member that genuinely needs none — which is how "
    f"a ledger-reading member would be handed back to a gate Job holding no ledger"
)


@dataclass(frozen=True, kw_only=True)
class AuthorityDeclarationMalformed:
    """A member's declaration names neither authority the contract knows.

    A registry bug — a typo, or a word nobody has ratified — not an expected
    runtime condition of a correctly-declared repository. It rides the failure
    track so that something is obliged to name it: folded into the
    runs-in-the-Job default, a mistyped declaration would behave exactly like an
    absent one and the member would keep failing in a pod that cannot answer for
    it, which is indistinguishable from the defect before this module existed.
    """

    target: str
    value: str
    reason: str


def _inventory_lines(*, repo_root: Path) -> list[str]:
    """Every member line of the consumer's own check inventory, trimmed.

    An absent or unreadable inventory yields NO lines rather than a failure: a
    repository that declares no inventory has no member that could carry an
    annotation, and returning a failure here would refuse the delegated gate of
    every consumer whose aggregate is declared somewhere else entirely.
    """
    try:
        raw = (repo_root / _INVENTORY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    trimmed = [line.strip() for line in raw.splitlines()]
    return [line for line in trimmed if line.startswith(_SLUG_PREFIX)]


def _inventory_member(*, line: str) -> str:
    """The member name an inventory line declares, without its annotations."""
    return line.split("#", 1)[0].strip()


def _declared_authority(*, line: str) -> str | None:
    """The authority this inventory line declares, or None when it declares none."""
    matched = _INVENTORY_DECLARATION.search(line)
    if matched is None:
        return None
    return matched.group("value")


def repository_authority_members(
    *, repo_root: Path
) -> IOResult[tuple[str, ...], AuthorityDeclarationMalformed]:
    """Name the members of `repo_root`'s check set that a gate Job must not run.

    In INVENTORY ORDER, so a caller reports the members it moved onto the
    pushing host in the same order the aggregate lists them. The FIRST malformed
    declaration fails the whole resolution: a caller is deciding what NOT to run
    on a cluster and what to run against a credential instead, and a partial
    classification whose remainder was never examined is not a classification.
    """
    declaring: list[str] = []
    for line in _inventory_lines(repo_root=repo_root):
        declared = _declared_authority(line=line)
        if declared is None:
            continue
        member = _inventory_member(line=line)
        if declared not in _AUTHORITIES:
            return IOFailure(
                AuthorityDeclarationMalformed(
                    target=member, value=declared, reason=_MALFORMED_REASON
                )
            )
        declaring.append(member)
    return IOSuccess(tuple(declaring))


def _write(*, text: str) -> None:
    """Write text to stdout and flush; discards the byte-count return value."""
    _ = sys.stdout.write(text)
    _ = sys.stdout.flush()


def _members_report(*, repo_root: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Print the members a gate Job must not run, or refuse naming the one it cannot read.

    FAIL-CLOSED by printing NOTHING on the failure track. An empty report that
    exited zero would read as "no member needs the pushing host", which is the
    answer that puts every authority-reading member back inside a pod holding no
    authority — so the exit code carries the refusal and the caller is expected
    to stop rather than narrow anything.
    """
    resolved = repository_authority_members(repo_root=repo_root)
    if not is_successful(resolved):
        malformed = unsafe_perform_io(resolved.failure())
        log.error(
            "check authority: declaration is malformed",
            member=malformed.target,
            value=malformed.value,
            reason=malformed.reason,
        )
        return 1
    members = unsafe_perform_io(resolved.unwrap())
    _write(text="".join(f"{member}\n" for member in members))
    return 0


def main() -> int:
    """The one answer a delegated gate Job's member list needs."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("check_authority")

    parser = argparse.ArgumentParser(
        description="Which check-set members read an authorization held outside the tree.",
    )
    _ = parser.add_argument(
        "command",
        choices=[_MEMBERS],
        help="'members' prints this repository's authority-declaring check-set members.",
    )
    _ = parser.parse_args()
    return _members_report(repo_root=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
