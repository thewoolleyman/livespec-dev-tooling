"""no_direct_github_access — first-party GitHub traffic goes through the budgeted client.

The Verifier half of the GitHub request-budget concern (livespec core epic
livespec-httc; work-item livespec-dev-tooling-t2q4). Its Mechanism half is
`livespec_dev_tooling.budgeted_gh.gh_read`, the ONE sanctioned `gh` read
boundary, and its Retrofit half (livespec-dev-tooling-z69s, PR #2268) routed
the enforcement suite's own forge reads through it. Nothing until now stopped
the next call site from spawning `gh` at the point of use again, so the
discipline held only for as long as everyone remembered it.

WHAT IS FLAGGED — the two AST shapes direct access actually takes here:

1. An argv SEQUENCE whose first element is the string `gh`. This is the shape
   rather than "a call to `subprocess.run`" on purpose: the spawn and the argv
   are routinely separated (`argv = ("gh", *args)` on one line, `subprocess.run(
   list(argv), ...)` several lines down, behind a `GhRunner` Protocol), so a
   matcher keyed on the CALL sees a variable and reports nothing. Keying on the
   sequence literal covers `run`, `Popen`, `check_output` and this repo's
   runner seams with one rule and no per-seam enumeration.
2. A string constant naming the GitHub API host. Catches the urllib and
   `http.client` paths, whose target is a URL rather than an argv — including
   the f-string form, whose literal chunk carries the host as an ordinary
   `ast.Constant`.

The `shell=True` string form (`subprocess.run("gh api ...", shell=True)`) is
NOT a third rule because it cannot occur: ruff `S602` bans `shell=True` across
this package, so there is no reachable spelling for it to match.

PROSE IS NOT A CALL SITE. A bare string expression — a module, class or
function docstring — is excluded from shape 2. Every module in this package
documents its own forge posture, and a check that convicted a file for
DESCRIBING the host would make the rationale unwriteable, which is the
opposite of what an exemption-by-documentation policy needs.

⛔ IT MUST NOT PASS VACUOUSLY. This suite has already shipped checks that were
green while scanning nothing (`check-public-api-result-typed` is green in all
nine fleet repos and scans zero files in every one). So the scanned-file count
is REPORTED on every run, and a run that scanned ZERO files FAILS rather than
passing — emptiness is a defect in the scan, never a clean bill of health.

THE SCANNED SET IS THE SUITE'S EXISTING FIRST-PARTY UNIVERSE
(`config.resolve_check_universe`), not a walk of this check's own. That is a
correctness requirement in three directions, each of which has already been
paid for once:

- It excludes any path with a `_vendor` SEGMENT. Three earlier checks
  re-derived their own file set without that exclusion and made vendoring
  uncommittable. It is also what realizes two of this check's three
  specified exemptions: the vendored budget client under
  `_vendor/livespec_runtime/github_budget*` and `livespec_runtime.github_auth`
  (whose `mint` documents in place why it reaches GitHub through urllib rather
  than a `gh` subprocess) are BOTH under `_vendor/`, so the shared filter drops
  them before this check ever opens a file. They need no registry entry here,
  and giving them one would leave two entries that can never match — the
  unexaminable rot an exemption list is supposed to avoid.
- It walks the git INDEX, so mutmut's generated `mutants/` tree is gone with
  the rest of the gitignored scratch. A prototype run on 2026-08-08 that walked
  the filesystem instead reported HUNDREDS of sites here instead of seven, one
  per mutant copy of a single real call site — phantom violations in generated
  code no one can fix. A check that cries wolf gets switched off, which ends in
  the same place as a check that is silently green.
- It excludes the test tree, so a test that ASSERTS on this ban (this module's
  own fixtures name both banned shapes) is not itself convicted by it.

EXEMPTIONS ARE A DOCUMENTED SEVERITY LEVER, NEVER A SILENT SKIP. Every entry in
`EXEMPTIONS` carries its reason in the PARSED VALUE, and every exemption the
run APPLIES is logged with that reason and with the number of sites it
excused — so an operator reading the check's output sees what was forgiven and
why, rather than seeing nothing. Two of the four entries record a MECHANISM GAP
rather than a settled posture, and say so; they are the follow-on work, not a
verdict that the sites are fine.

⚠️ WHY THIS MODULE LIVES OUTSIDE `livespec_dev_tooling/checks/`, AND THEREFORE
OUTSIDE THE CANONICAL FLEET-UNIVERSAL SLUG SET. `canonical_checks` discovers
`checks/<slug>.py` by filesystem walk, so a module placed there becomes an
OBLIGATION on all nine fleet members at their next pin bump. Two measured facts
make that unshippable today, and neither is fixable from inside this
repository:

- Direct GitHub access still exists in first-party code in three siblings —
  livespec (4 sites), livespec-runtime (4 after its own exempt mint constant),
  and livespec-orchestrator-beads-fabro (12). None routes through the
  sanctioned client. livespec's `SPECIFICATION/non-functional-requirements.md`
  §"Fleet membership contract" requires under New-obligation discipline that a
  change adding an obligation wire all current members in the SAME change, so
  that the fleet is never red by construction the moment a rule lands. That
  20-site cross-repo retrofit is not this work-item's scope, and this
  repository has already paid once for the reverse order: the Railway
  decoupling armed a check ahead of adoption, turned five repos red and was
  reverted.
- The anti-vacuous guard above would hard-fail livespec-console-beads-fabro
  independently of any violation. That member has genuinely ZERO first-party
  `.py` — `config.iter_first_party_py_files` records it as the verified
  codeless case — so a canonical slug that fails on an empty scope breaks it on
  arrival with nothing to fix.

Repo-private placement is the mechanism this repository already uses for
exactly this, and says so: `fabro_image_pin_lockstep` records that its module
"deliberately lives OUTSIDE livespec_dev_tooling/checks/ so it stays out of the
canonical fleet-universal slug set". The ban is armed UNCONDITIONALLY here —
`just check` runs it on every commit and push with no lever, no warn-only mode
and no skip — and promotion to the canonical set is a follow-on that travels
WITH the fleet retrofit, which is the order the membership contract requires.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in `livespec_dev_tooling/**`. Diagnostics
flow through structlog (JSON to stderr); the vendored copy under
`livespec_dev_tooling/_vendor` is added to `sys.path` at import time.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import resolve_check_universe  # noqa: E402

__all__: list[str] = []


# The one sanctioned path, named in the failure message so a convicted call
# site is told where to go rather than merely what not to do.
SANCTIONED_CLIENT = "livespec_dev_tooling.budgeted_gh.gh_read"

_GH_BINARY = "gh"
_GITHUB_API_HOST = "api.github.com"

_KIND_GH_ARGV = "gh-argv"
_KIND_GITHUB_API_HOST = "github-api-host"

_BANNED_EVENT = f"direct GitHub access is banned — route it through {SANCTIONED_CLIENT}"
_EMPTY_SCOPE_EVENT = (
    "scanned ZERO first-party files — the scan found nothing to judge, which is a "
    "defect in the scan and not a clean result"
)


@dataclass(frozen=True, kw_only=True)
class Exemption:
    """One documented, path-scoped licence to reach GitHub directly.

    `reason` is carried in the PARSED VALUE rather than in a comment beside
    it, because the reason is what makes this a severity lever rather than a
    silent skip: the check logs it on every run that applies the entry, so the
    forgiveness is visible in the same output as the convictions.
    """

    path: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class Site:
    """One direct-GitHub-access site: where it is, and which shape matched."""

    line: int
    kind: str


# ⛔ NOT A LIST TO GROW BY REFLEX. Each entry states why the sanctioned client
# is the WRONG answer for that file — not that routing it is inconvenient —
# and the two that record a MECHANISM GAP name the work that retires them.
EXEMPTIONS: tuple[Exemption, ...] = (
    Exemption(
        path="livespec_dev_tooling/budgeted_gh.py",
        reason=(
            "The chokepoint itself. This module IS the sanctioned client's spawn, so "
            "the one `gh` argv it builds is the boundary every other site is being "
            "sent to rather than a bypass of it."
        ),
    ),
    Exemption(
        path="livespec_dev_tooling/no_direct_github_access.py",
        reason=(
            "The detector itself. It carries the GitHub API host as its MATCH PATTERN, "
            "never as a request target; it opens no socket and spawns nothing. Without "
            "this entry the ban would convict the only file that enforces it."
        ),
    ),
    Exemption(
        path="livespec_dev_tooling/cross_repo/release_lane_issue_runner.py",
        reason=(
            "Stdlib-only BY NECESSITY, documented in place: `gh` is not installed on "
            "the self-hosted runner this module executes on, and the first version of "
            "its sibling died there with FileNotFoundError. Routing it through the "
            "sanctioned client — which spawns `gh` — would break it in its only venue. "
            "Same class as the `livespec_runtime.github_auth.mint` exemption the "
            "concern already blesses, and reached by the same reasoning."
        ),
    ),
    Exemption(
        path="livespec_dev_tooling/cross_repo/release_lane_watch_runner.py",
        reason=(
            "Stdlib-only BY NECESSITY, documented in place, for the reason its issue-"
            "producing sibling records: `gh` is absent on the self-hosted runner these "
            "two run on, so urllib is the only transport available to them."
        ),
    ),
    Exemption(
        path="livespec_dev_tooling/fleet/_gh_runner.py",
        reason=(
            "MECHANISM GAP, not a settled posture. This seam needs STDIN (its "
            "`GhRunner` Protocol takes it) and carries its own measured pacing floor, "
            "cooldown and Retry-After schedule; `gh_read` accepts no stdin and is "
            "built with `max_attempts=1`, so there is no sanctioned path to point it "
            "at today. Arming the ban over a call site with no permitted alternative "
            "would fail it with no remedy. Retiring this entry means extending the "
            "budgeted client to carry stdin, which belongs to the concern's Mechanism "
            "slot rather than to its Verifier."
        ),
    ),
    Exemption(
        path="livespec_dev_tooling/fleet/_snapshot.py",
        reason=(
            "MECHANISM GAP, not a settled posture. This seam streams a BINARY payload "
            "to a file handle; `gh_read` captures text and returns it, and capturing a "
            "gzip stream through a locale codec hands back a corrupted archive that "
            "fails later at extraction, naming the wrong thing. Retiring this entry "
            "means a binary-sink form of the budgeted client — again Mechanism work, "
            "not Verifier work."
        ),
    ),
)


def _is_gh_argv(*, node: ast.List | ast.Tuple) -> bool:
    """True for a sequence literal whose FIRST element is the string `gh`."""
    if not node.elts:
        return False
    first = node.elts[0]
    return isinstance(first, ast.Constant) and first.value == _GH_BINARY


def _names_github_api_host(*, node: ast.Constant, prose: frozenset[int]) -> bool:
    """True for a non-prose string constant that names the GitHub API host."""
    if not isinstance(node.value, str):
        return False
    return _GITHUB_API_HOST in node.value and id(node) not in prose


def _prose_constant_ids(*, tree: ast.Module) -> frozenset[int]:
    """Identify the string constants that are bare expressions — i.e. docstrings."""
    return frozenset(
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    )


def scan_source(*, source: str) -> tuple[Site, ...]:
    """Report every direct-GitHub-access site in one module's source.

    Pure: takes the bytes, returns the findings, reads nothing and spawns
    nothing. The IO — resolving the universe and opening each file — belongs
    to `main`.
    """
    tree = ast.parse(source)
    prose = _prose_constant_ids(tree=tree)
    sites: list[Site] = []
    for node in ast.walk(tree):
        # The isinstance arms are here rather than inside the predicates so
        # pyright can see that `lineno` exists on the narrowed node; `ast.AST`
        # itself carries no position.
        if isinstance(node, ast.List | ast.Tuple):
            if _is_gh_argv(node=node):
                sites.append(Site(line=node.lineno, kind=_KIND_GH_ARGV))
        elif isinstance(node, ast.Constant) and _names_github_api_host(node=node, prose=prose):
            sites.append(Site(line=node.lineno, kind=_KIND_GITHUB_API_HOST))
    return tuple(sorted(sites, key=lambda site: (site.line, site.kind)))


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_direct_github_access")
    root, universe = resolve_check_universe()
    exempt_by_path = {exemption.path: exemption for exemption in EXEMPTIONS}
    excused: list[tuple[Exemption, int]] = []
    offenders: list[tuple[Path, Site]] = []
    for rel in universe:
        sites = scan_source(source=(root / rel).read_text(encoding="utf-8"))
        exemption = exempt_by_path.get(rel.as_posix())
        if exemption is not None:
            excused.append((exemption, len(sites)))
            continue
        offenders.extend((rel, site) for site in sites)
    # The scanned count is reported BEFORE any verdict, on every run, so a
    # green result can be told apart from a scan that never opened a file.
    log.info(
        "scanned first-party Python for direct GitHub access",
        scanned=len(universe),
        exemptions_applied=len(excused),
        sites=len(offenders),
        sanctioned_client=SANCTIONED_CLIENT,
    )
    for exemption, site_count in excused:
        log.info(
            "documented exemption applied — a severity lever, not a silent skip",
            file=exemption.path,
            excused_sites=site_count,
            reason=exemption.reason,
        )
    if not universe:
        log.error(_EMPTY_SCOPE_EVENT, scanned=0)
        return 1
    for rel, site in offenders:
        log.error(_BANNED_EVENT, file=rel.as_posix(), line=site.line, shape=site.kind)
    return 1 if offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
