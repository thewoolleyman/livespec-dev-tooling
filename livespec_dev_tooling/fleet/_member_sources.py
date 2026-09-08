"""_member_sources — read one member's two source universes from a snapshot.

The I/O half of the fleet consumption oracle: `_public_api_graph` takes source
TEXT and computes who consumes whom; this module turns a
`FleetContext.member_tree_snapshot` root into the text it takes. They are
separate modules because one reaches the filesystem and the other cannot, and
because the graph's correctness content is worth testing without a tree on
disk at all.

THE WALK IS TRACKED-ONLY, AND WHICH MECHANISM SUPPLIES "TRACKED" DEPENDS ON
THE VANTAGE. A snapshot is an ARCHIVE OF A REF: it already holds exactly the
tracked files, so there is no index to consult and no ignored scratch to
filter, and an `rglob` over it IS the tracked set. A LOCAL CHECKOUT — the
self-member vantage `_rows_public_api_conformance._local_root_for` binds — is
the opposite, and livespec-dev-tooling-xs58 measured what that cost: an entire
`.venv/lib/python3.10/site-packages/**` tree reached `filter_first_party_py`
through a parameter literally named `tracked_py`, and entered the member's
first-party DEFINING universe. The predicate has no `.venv` arm and needs none
— a gitignored virtualenv is never `git ls-files`-tracked, so it could never
arrive — so the repair belongs HERE, in the walk that feeds it, and not in the
predicate. That population defect was invisible for as long as the graph only
emitted edges for imports that RESOLVE; a vendored `dataclasses.py` under
site-packages is exactly what makes a stdlib name resolve to a "first-party"
definer, so no "skip when no candidate resolves" fence could have covered it.

The discriminator between the two vantages is a `.git` at the ROOT rather than
a `git ls-files` exit code, because ls-files run inside an untracked directory
that happens to sit under some unrelated repo exits 0 with an EMPTY listing —
a silently empty member instead of a loud failure, which is the worse of the
two ways to be wrong.

A FILE TRACKED BUT DELETED from the working tree is DROPPED: the index lists
it, so the listing is intersected with what is on disk. What this module
produces is source TEXT, which a deleted file has none of at this vantage, and
the local vantage exists to grade a member on the tree it ACTUALLY has — so a
mid-edit deletion is an absent source here, not a whole member lost to
`MemberSourcesUnreadable` by a read of a path that is gone.

The DEFINING universe is `filter_first_party_py` — the same predicate
`resolve_check_universe()` applies in a checkout, so what this row scopes and
what `public_api_result_typed` scopes locally are the same set by
construction rather than by agreement. It inherits that predicate's known
gap: `livespec-dev-tooling-995m` records that `is_generated` excludes any file
carrying `@generated` in a `#` comment, which in this repo silently excludes
`config.py` from every universe derived this way.

EVERY READ FAILURE NAMES ITS FILE, and that is why the reads happen before the
classification rather than after. `UnicodeDecodeError` carries the offending
BYTES and no filename, so a decode failure escaping a walk could only be
reported against the walk ROOT — and an operator reading it is looking at a
materialized copy of ANOTHER repo's tree, where "some file did not decode" is
not something they can act on. Reading in a loop that already holds the path
gets that for free, without a second copy of the re-raise trick
`cross_repo/_pin_directory_scan_formats.read_pin_text` uses where the path is
not in hand.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.config import (  # noqa: E402
    filter_first_party_py,
    list_tracked_py,
    role_path,
)
from livespec_dev_tooling.fleet._public_api_graph import MemberSources  # noqa: E402

if TYPE_CHECKING:
    from livespec_dev_tooling.config import Config

__all__: list[str] = [
    "MemberSourcesUnreadable",
    "read_member_sources",
]


_CONFTEST_NAME = "conftest.py"


@dataclass(frozen=True, kw_only=True)
class MemberSourcesUnreadable:
    """A file in the member's snapshot could not be read as UTF-8 text."""

    file: str
    detail: str


def _walk_py(*, root: Path) -> tuple[Path, ...]:
    """Every TRACKED `.py` under `root`, repo-root-relative and sorted.

    A checkout is read from the git INDEX and an archive by `rglob`, per the
    module docstring's two-vantage rule; `.git` at the root is what tells them
    apart. The index listing is intersected with what is on disk, so a tracked
    path deleted from the working tree drops out.
    """
    if not (root / ".git").exists():
        return tuple(sorted(path.relative_to(root) for path in root.rglob("*.py")))
    return tuple(sorted(rel for rel in list_tracked_py(repo_root=root) if (root / rel).is_file()))


def _is_test_source(*, rel: Path, tests_tree_prefix: str) -> bool:
    """True for the files `filter_first_party_py` excludes as test scaffolding.

    This MIRRORS that function's test clause rather than deriving from it, and
    the mirror is deliberate: the two are complements of one partition, and
    there is no way to ask `filter_first_party_py` "which did you drop, and
    why". Kept adjacent in wording to the original so a change there is
    visible as a divergence here.
    """
    return rel.as_posix().startswith(tests_tree_prefix) or rel.name == _CONFTEST_NAME


def read_member_sources(
    *, root: Path, config: Config
) -> IOResult[MemberSources, MemberSourcesUnreadable]:
    """The member's DEFINING and CONSUMING source universes, or the file that failed.

    `IOResult` rather than `Result`: this walks a directory and reads every
    file in it with no seam in between, which is what livespec v179 member 1
    clause (c) sees and is the honest type.

    The consuming universe is the defining one PLUS the member's test tree,
    because v178 form 2 is a cross-repo TEST import. A same-repo test importer
    is still not a consumer — that falls out of the graph emitting only
    cross-member edges, so it needs no filtering here.
    """
    reading = root
    try:
        candidates = _walk_py(root=root)
        texts: dict[Path, str] = {}
        for rel in candidates:
            reading = root / rel
            texts[rel] = reading.read_text(encoding="utf-8")
        reading = root
        neutral_hook_body = role_path(role=config.neutral_hook_body_path)
        defining = filter_first_party_py(
            tracked_py=candidates,
            repo_root=root,
            tests_tree_prefix=config.tests_tree_prefix,
            neutral_hook_body_path=(
                None if neutral_hook_body is None else neutral_hook_body.as_posix()
            ),
        )
    except (OSError, UnicodeDecodeError) as unreadable:
        # ONE arm over both flavors, and `reading` rather than the exception
        # names the file: an `OSError` populates `filename` but a
        # `UnicodeDecodeError` carries only the offending bytes, so reading the
        # path off the exception would name the file for one flavor and the
        # walk root for the other — the weaker diagnostic winning silently.
        return IOFailure(MemberSourcesUnreadable(file=str(reading), detail=str(unreadable)))
    consuming = {
        rel: text
        for rel, text in texts.items()
        if rel in frozenset(defining)
        or _is_test_source(rel=rel, tests_tree_prefix=config.tests_tree_prefix)
    }
    return IOSuccess(
        MemberSources(defining={rel: texts[rel] for rel in defining}, consuming=consuming)
    )
