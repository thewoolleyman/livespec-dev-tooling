"""_heading_coverage_spec_first — the bounded spec-first admission of new debt.

Ratified into this repository's `SPECIFICATION/non-functional-requirements.md`
at v067, as the ONE exception to the shrink-only rule the sibling directions
enforce:

> A new register key MAY be admitted as spec-first debt ONLY when the same
> authored change introduces its exact H2 heading into the governed live
> specification, that heading and its coverage key are both absent from the
> comparable pre-change `HEAD` specification and coverage registry, the new
> coverage row declares `test: "TODO"` with a nonempty `work_item` and an
> acknowledgment that a real test at the required tier is owed, and mechanical
> regeneration supplies the matching owner and a `first_seen` date.

WHY AN EXCEPTION EXISTS AT ALL, AND WHY IT IS THIS NARROW. The shrink-only
direction reads the SET of register keys and nothing else, so it cannot tell a
laundered entry from the one shape a spec-first repository legitimately
produces: a ratification lands a new `## Scenario:` heading, `heading_coverage`
demands a coverage row for it the same commit, and no real test can exist yet
because the implementation item has not run. Without the exception that commit
is unlandable and the only way out is to stop writing specifications first.

Every condition is therefore read from REPOSITORY DATA at two revisions — the
governed spec file and the coverage registry, in the working tree and at `HEAD`
— so there is nothing for an author to assert. That is what separates an
exception from an exemption list: the admission cannot be requested, only
earned, and the evidence that earns it is the same evidence a reviewer reads.

⛔ THE H2 SET IS RESTATED HERE RATHER THAN SHARED WITH `heading_coverage`. That
check's `_extract_h2_headings` is module-private and serves a different walk —
every template-declared spec file at every spec-tree root, in the working tree
only — while this module reads ONE named file at TWO revisions. Importing a
private name across a module boundary is refused by `private_calls` and by
pyright's `reportPrivateUsage`, and promoting one shared scanner would couple
the debt ratchet to the coverage check it has no other relationship with. The
two MAY disagree only in the fail-closed direction: a heading this scanner
misses is a heading whose debt is REFUSED, never one silently admitted.

Output discipline: this module DECIDES and emits nothing — the caller owns
every diagnostic — so `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) have nothing to ban here.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.heading_coverage_debt import (  # noqa: E402
    COVERAGE_PATH,
    head_rows,
    head_text,
    register_key,
)

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage_debt_register.py`, so pyright's per-file analysis
# does not flag them unused across the package boundary.
__all__: list[str] = [
    "spec_first_admitted",
]


def _h2_headings(*, source: str) -> frozenset[str]:
    """The exact H2 headings in `source`, trailing whitespace stripped.

    A `### ` line does not start with `## ` and so is excluded without a second
    test; the registry's `heading` field carries the `## ` prefix verbatim, which
    is what makes an EXACT comparison possible rather than a prefix match.
    """
    return frozenset(
        stripped
        for stripped in (line.rstrip() for line in source.splitlines())
        if stripped.startswith("## ")
    )


def _live_headings(*, cwd: Path, spec_root: str, spec_file: str) -> frozenset[str] | None:
    """The working-tree H2 set of a governed spec file; `None` when it cannot be read.

    `None` is the UNREADABLE answer and never an empty set: a spec file this run
    cannot open proves nothing about whether a heading is new, and reading it as
    "no headings" would refuse every admission while LOOKING like a verdict
    about the heading.
    """
    try:
        source = (cwd / spec_root / spec_file).read_text(encoding="utf-8")
    except OSError:
        return None
    return _h2_headings(source=source)


def _head_headings(*, cwd: Path, spec_root: str, spec_file: str) -> frozenset[str] | None:
    """The `HEAD` H2 set of a governed spec file; `None` when HEAD carries no copy.

    The mirror of `_live_headings` on the other revision, and the same
    distinction: `None` means no comparison is possible — not a repository, no
    such blob, a spec file this change creates outright — which cannot establish
    that a heading is new.
    """
    committed = head_text(cwd=cwd, path=Path(spec_root) / spec_file)
    if isinstance(committed, IOFailure):
        return None
    return _h2_headings(source=unsafe_perform_io(committed.unwrap()))


def _keys(*, rows: list[dict[str, object]]) -> frozenset[tuple[str, str, str]]:
    """The register keys `rows` carries; unkeyed rows place nothing."""
    return frozenset(key for key in (register_key(row=row) for row in rows) if key is not None)


def _head_registry_keys(*, cwd: Path) -> frozenset[tuple[str, str, str]] | None:
    """Every coverage key `HEAD`'s registry carries; `None` when it is incomparable.

    EVERY key, not only the `TODO` ones: the ratified clause requires the
    coverage key to be absent from `HEAD`'s registry outright, which is what
    refuses a real-test-to-`TODO` regression. A key that already had a row is
    not a new heading's key whatever that row said.
    """
    committed = head_rows(cwd=cwd, path=COVERAGE_PATH)
    return (
        None
        if isinstance(committed, IOFailure)
        else _keys(rows=unsafe_perform_io(committed.unwrap()))
    )


def _admits(
    *,
    cwd: Path,
    key: tuple[str, str, str],
    head_registry_keys: frozenset[tuple[str, str, str]] | None,
) -> bool:
    """Whether `key` is the bounded spec-first exception rather than plain growth.

    ONE conjunction, deliberately, because the ratified clause IS one: every
    condition must hold, and a key that fails any of them is the growth the
    shrink-only direction already named. Both spec revisions are read before the
    test rather than inside it, so an unreadable working tree and an
    incomparable `HEAD` are distinguishable answers rather than one short
    circuit.
    """
    spec_root, spec_file, heading = key
    live = _live_headings(cwd=cwd, spec_root=spec_root, spec_file=spec_file)
    before = _head_headings(cwd=cwd, spec_root=spec_root, spec_file=spec_file)
    return (
        head_registry_keys is not None
        and key not in head_registry_keys
        and live is not None
        and heading in live
        and before is not None
        and heading not in before
    )


def spec_first_admitted(
    *, cwd: Path, grown: list[tuple[str, str, str]]
) -> frozenset[tuple[str, str, str]]:
    """The subset of `grown` the bounded v067 spec-first exception admits.

    `grown` is the shrink-only direction's own finding set, passed in rather than
    recomputed, so the exception can only ever REMOVE a key the caller already
    convicted — it cannot invent an admission for a key no direction named.

    The evidence reads are skipped entirely when nothing grew, and that is
    load-bearing rather than an optimisation: the overwhelming majority of runs
    carry no growth at all, and a repository at zero debt must not be asked to
    open a spec file to confirm it.
    """
    if not grown:
        return frozenset()
    head_registry_keys = _head_registry_keys(cwd=cwd)
    return frozenset(
        key for key in grown if _admits(cwd=cwd, key=key, head_registry_keys=head_registry_keys)
    )
