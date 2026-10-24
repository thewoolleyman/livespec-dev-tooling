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

WHICH MEMBERS ARE EXAMINED, and why that is not simply "the inventory's". The
resolution must cover the members the repository's aggregate ACTUALLY SELECTS,
and a `check-targets.txt` is only one of the two shapes this fleet declares an
aggregate in. A repository carrying no inventory declares its check set in the
`targets=(...)` array of its bare `check:` recipe — the surface
`canonical_recipe_fidelity` and the fleet's aggregate-wiring rows already read —
so that array is what this module falls back to in the inventory's absence. The
inventory keeps PRECEDENCE where it exists, because it is the only surface a
REPO-PRIVATE member's declaration can ride: the array's lines are read for their
slugs alone, so in a no-inventory repository only a SHIPPED check's own module
constant can declare an authority, and a repo-private member that needs one is
declared by adding the inventory file.

WITHOUT THAT FALLBACK THE WHOLE EXCEPTION WAS INERT IN SIX OF EIGHT FLEET
MEMBERS. Measured on v1.127.0: `check_authority members` printed two names in
this repository, which carries the inventory, and NOTHING in livespec-overseer
or livespec-orchestrator-beads-fabro, which do not — so the client handed their
forge-admin member straight to a Job that by design holds no admin token.
Measured again end to end on 2026-10-24 01:41-01:45Z: cluster gate Job
`gate-livespec-overseer-tpfd2` ran overseer's master e4a81525 green on every
member except `check-branch-protection-alignment`, which got `gh: Resource not
accessible by personal access token (HTTP 403)` and then refused to report a
pass it had not verified. An empty answer is the one answer that puts every
authority-reading member back inside a pod holding no authority, which is why
reaching it through a missing FILE is no better than reaching it through a bad
DECLARATION.

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
        Print, one per line, the members of THIS repository's own check set
        that declare they read an authorization held outside the tree — the
        set a delegated gate Job must not run, in the order its aggregate
        lists them.
        Exit 1, having printed nothing, when a declaration cannot be read.

Output discipline: the `members` subcommand writes its one-name-per-line report
to stdout, which is why this file is declared in this repository's
`supervisor_entry_files`. Diagnostics stay on stderr as structlog JSON.
"""

from __future__ import annotations

import argparse
import ast
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

from livespec_dev_tooling.checks._tool_backed_surfaces import (  # noqa: E402  — same.
    extract_check_recipe_body,
    extract_targets_array_tokens,
)

__all__: list[str] = []

# The two authorities the ratified bullet names: the work-items ledger (for
# example a maintainer approval label) and the forge's repository administration
# settings. A CLOSED vocabulary rather than a free-text reason, so a member
# cannot leave the gate Job on a declaration nothing can act on.
LEDGER = "ledger"
FORGE_ADMIN = "forge-admin"

# A SHIPPED check's own declaration: a module-level constant in its
# `livespec_dev_tooling/checks/<slug>.py`, deliberately absent from that
# module's `__all__` because nothing imports it — declaring it an export would
# claim a consumption that does not exist.
DECLARATION_NAME = "CHECK_AUTHORITY"

_AUTHORITIES = frozenset({LEDGER, FORGE_ADMIN})

_INVENTORY_NAME = "check-targets.txt"
_JUSTFILE_NAME = "justfile"
_SLUG_PREFIX = "check-"
_MEMBERS = "members"
_CHECKS_PACKAGE_DIR = Path(__file__).resolve().parent / "checks"

# A repo-private member's declaration: a trailing `# authority: <value>` comment
# on its inventory line, beside the `# purity:` annotation that is already there.
_INVENTORY_DECLARATION = re.compile(r"#\s*authority:\s*(?P<value>\S+)")

# What a `CHECK_AUTHORITY` that is not a static string literal resolves to. It
# names no authority, so it reaches the malformed track — a computed declaration
# cannot be read without importing the module, and a declaration nothing can
# read is worse than none at all, because it LOOKS declared.
_NOT_A_STRING_LITERAL = "<not-a-string-literal>"

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


def _inventory_lines(*, repo_root: Path) -> list[str] | None:
    """Every member line of the consumer's own check inventory, trimmed, or None.

    TRI-STATE, and the third state is the whole point: `None` means this
    repository declares NO inventory, which is different from declaring an
    inventory that lists no member. The caller falls back to the justfile
    aggregate on the first and must not on the second — a repository that
    carries the file has said where its declarations live, and reading its
    justfile instead would silently drop every repo-private annotation while
    still answering plausibly.

    An UNREADABLE inventory joins the absent case rather than refusing, for the
    reason the module docstring gives for every no-claim reading here: the
    fallback still covers the members the aggregate selects, and refusing would
    refuse the delegated gate of a whole repository over one unreadable file.
    """
    try:
        raw = (repo_root / _INVENTORY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    trimmed = [line.strip() for line in raw.splitlines()]
    return [line for line in trimmed if line.startswith(_SLUG_PREFIX)]


def _aggregate_targets(*, repo_root: Path) -> list[str]:
    """Every `check-` slug the consumer's own `just check` aggregate selects.

    Read through the SHARED justfile readers rather than a fourth private copy
    of them, so this module and the checks that already enforce that array's
    membership — `aggregate_completeness`, `canonical_recipe_fidelity`, the
    fleet's aggregate-wiring row — cannot come to disagree about which members a
    repository's aggregate selects. A disagreement here is invisible: both
    answers are a plausible list of slugs.

    A SHAPE THIS READER CANNOT ENUMERATE DECLARES NOTHING, which is the same
    direction an absent inventory takes. A repository with no bare `check:`
    recipe, or whose recipe carries no literal `targets=(...)` array, has no
    selected member that could carry a declaration, so there is nothing to
    misread — and refusing instead would refuse the delegated gate of every
    consumer whose aggregate is shaped some other way.
    """
    try:
        justfile_text = (repo_root / _JUSTFILE_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    recipe_body = extract_check_recipe_body(justfile_text=justfile_text)
    if not is_successful(recipe_body):
        return []
    targets = extract_targets_array_tokens(recipe_body=recipe_body.unwrap())
    if not is_successful(targets):
        return []
    return targets.unwrap()


def _declaring_lines(*, repo_root: Path) -> list[str]:
    """The lines whose declarations decide this repository's gate-Job member list.

    The inventory's when it carries one — annotations and all —, else the bare
    slugs its `just check` aggregate selects. Returned as LINES rather than as
    slugs because the two surfaces differ in exactly one way: an inventory line
    can carry the `# authority:` annotation a repo-private member needs, and a
    justfile-derived slug cannot, so a slug reaches the annotation reader and is
    correctly read as annotating nothing.
    """
    inventory = _inventory_lines(repo_root=repo_root)
    if inventory is not None:
        return inventory
    return _aggregate_targets(repo_root=repo_root)


def _inventory_member(*, line: str) -> str:
    """The member name an inventory line declares, without its annotations."""
    return line.split("#", 1)[0].strip()


def _inventory_annotation(*, line: str) -> str | None:
    """The authority this inventory line annotates, or None when it annotates none."""
    matched = _INVENTORY_DECLARATION.search(line)
    if matched is None:
        return None
    return matched.group("value")


def _module_path_for(*, target: str) -> Path | None:
    """The shipped check module backing `target`, when this library ships one.

    `check-kebab-case` maps to `checks/snake_case.py` — the same mapping
    `canonical_checks` walks in the other direction. A target whose module this
    installed library does not ship has no module to ask and falls through to
    the consumer's own declaration. Every caller resolves a `check-` slug, so the
    prefix is stripped rather than re-tested here.
    """
    module = target[len(_SLUG_PREFIX) :].replace("-", "_")
    path = _CHECKS_PACKAGE_DIR / f"{module}.py"
    if not path.is_file():
        return None
    return path


def _declared_constant(*, node: ast.stmt) -> str | None:
    """The `CHECK_AUTHORITY` value this module-level statement declares, if any.

    Both spellings are accepted — the bare `CHECK_AUTHORITY = "..."` assignment
    and the annotated `CHECK_AUTHORITY: str = "..."` — because the two say the
    same thing and a resolver reading only one would report a correctly
    declared module as declaring nothing, which runs in the unsafe direction
    here: the member goes back into a pod that cannot answer for it. A statement
    assigning the name something other than a string literal returns
    `_NOT_A_STRING_LITERAL`, which no vocabulary value matches, so it is
    convicted rather than passed over.
    """
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return None
    if not any(isinstance(item, ast.Name) and item.id == DECLARATION_NAME for item in targets):
        return None
    assigned = node.value
    if isinstance(assigned, ast.Constant) and isinstance(assigned.value, str):
        return assigned.value
    return _NOT_A_STRING_LITERAL


def _declaration_in_module(*, path: Path) -> str | None:
    """The module's own `CHECK_AUTHORITY` declaration, read statically.

    A module that cannot be read or parsed has made NO claim, and the safe
    reading of no claim is the runs-in-the-Job default — so this returns None
    rather than refusing. The direction is the opposite of a MALFORMED
    declaration's and deliberately so: there something was written and cannot be
    acted on, which is a registry bug; here nothing was written at all, and
    refusing would make one syntactically broken check module refuse every
    delegated push in the fleet. It never imports the module: a resolution runs
    on the pre-push path, where importing every check module to read one
    constant would pay that whole import cost for a classification.
    """
    try:
        parsed = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None
    for node in parsed.body:
        declared = _declared_constant(node=node)
        if declared is not None:
            return declared
    return None


def _declared_authority(*, target: str, line: str) -> str | None:
    """The authority `target` declares, preferring its own shipped module.

    A shipped check's own module OUTRANKS the consumer's inventory, and the
    precedence is load-bearing rather than arbitrary: the module declaration is
    the one that reaches every consuming repository, so one repository's
    inventory line must not be able to move a shipped member off the cluster —
    or back onto it — while the library says otherwise everywhere else.
    """
    module_path = _module_path_for(target=target)
    if module_path is not None:
        return _declaration_in_module(path=module_path)
    return _inventory_annotation(line=line)


def repository_authority_members(
    *, repo_root: Path
) -> IOResult[tuple[str, ...], AuthorityDeclarationMalformed]:
    """Name the members of `repo_root`'s check set that a gate Job must not run.

    IN AGGREGATE ORDER, so a caller reports the members it moved onto the
    pushing host in the same order the aggregate lists them — the inventory's
    order where the repository carries one, and its `check:` recipe's
    `targets=(...)` order where it does not. The FIRST malformed
    declaration fails the whole resolution: a caller is deciding what NOT to run
    on a cluster and what to run against a credential instead, and a partial
    classification whose remainder was never examined is not a classification.
    """
    declaring: list[str] = []
    for line in _declaring_lines(repo_root=repo_root):
        member = _inventory_member(line=line)
        declared = _declared_authority(target=member, line=line)
        if declared is None:
            continue
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
