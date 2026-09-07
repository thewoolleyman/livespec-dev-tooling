"""Version ordering over the pin tags the bump-PR decisions compare.

Split out of `bump_pr_supersession` at the cohesion seam between DECIDING which
bump PRs to close or refuse and ORDERING the tags those decisions compare over.

The tags are not bare semver: a fabro-sandbox pin carries a `<layer>-` prefix
over its `vX.Y.Z` release, and a bootstrap consumer's `compat.pinned` can still
read `master`. So the comparison reads the trailing version triple, and a tag it
cannot parse orders against nothing — every comparator below answers `False`
rather than guessing, which is what keeps an unparseable pin from being read as
superseding or superseded.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "version_gt",
    "version_gte",
    "version_lt",
    "version_sort_key",
]

_VERSION_RE = re.compile(r"(?:^|-)?v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


def _version_tuple(*, value: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.search(value)
    if match is None:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def version_sort_key(*, value: str) -> tuple[int, int, int]:
    """Return an ordering key for a pin tag; an unparseable tag sorts lowest."""
    return _version_tuple(value=value) or (0, 0, 0)


def version_gte(*, left: str, right: str) -> bool:
    """Return whether ``left`` is the same tag as, or a later version than, ``right``."""
    if left == right:
        return True
    left_tuple = _version_tuple(value=left)
    right_tuple = _version_tuple(value=right)
    if left_tuple is None or right_tuple is None:
        return False
    return left_tuple >= right_tuple


def version_gt(*, left: str, right: str) -> bool:
    """Return whether ``left`` is a strictly later version than ``right``."""
    left_tuple = _version_tuple(value=left)
    right_tuple = _version_tuple(value=right)
    if left_tuple is None or right_tuple is None:
        return False
    return left_tuple > right_tuple


def version_lt(*, left: str, right: str) -> bool:
    """Return whether ``left`` is a strictly earlier version than ``right``."""
    left_tuple = _version_tuple(value=left)
    right_tuple = _version_tuple(value=right)
    if left_tuple is None or right_tuple is None:
        return False
    return left_tuple < right_tuple
