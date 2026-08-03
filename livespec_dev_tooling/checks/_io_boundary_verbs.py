"""Which VERB means I/O when the receiver could not be resolved.

Extracted from `_io_boundary_calls` when that file reached the 250-LLOC hard
ceiling. The seam is the one its parent already draws in prose: the parent
answers "what is this call" by RESOLVING THE RECEIVER, and falls through to
here only when there is no binding to consult and the verb is all that is
left. Keeping the fallback's data and its one decision together makes the
non-conservative step a named surface rather than a trailing branch.
"""

from __future__ import annotations

import ast

__all__: list[str] = ["unresolved_receiver_call_is_io"]


# Verbs that decide an attribute call whose RECEIVER cannot be resolved. Every
# member is unambiguously a filesystem, process or socket operation on any
# plausible receiver.
#
# MEMBERSHIP NEEDS BOTH HALVES, AND THE SECOND IS WHAT THIS SET ADDS. livespec
# v184 section "ROP composition" section "What counts as an I/O boundary" makes FAILABILITY the
# criterion — a boundary is a primitive at which a failure can ORIGINATE — and
# every member below was driven with adverse input on CPython 3.10.16, the
# fleet's `requires-python` FLOOR, and raises for at least one. But failability
# is NECESSARY AND NOT SUFFICIENT here: with the receiver unresolved only the
# VERB is left, so the name must also be unambiguously an I/O surface.
#
# Deliberately ABSENT: `get`, `run`, `send`, `post`, `close`, `poll` — each is at
# least as often a mapping lookup or an injected seam in this codebase as it is
# I/O, and a name match on them is the exact defect that mis-flagged ten total
# functions.
#
# ⛔ AND `group` IS ABSENT FOR THAT SAME REASON DESPITE BEING FAILABLE — the
# third instance of that defect, measured. `Path.group()` raises
# `FileNotFoundError`, so it passes the failability half; `re.Match.group()` is a
# pure string operation that dominates the name here. Adding it moved this repo
# 24 -> 34 offenders and ALL TEN additions were `match.group(...)` sites, while
# `open` / `readlink` / `owner` / `truncate` together added ZERO. Pinned by
# `test_group_is_refused_despite_being_failable`.
#
# ⛔ ABSENT BY MEASURED DETERMINATION, not oversight — v184 requires the
# determination recorded WITH its evidence. `chown`, `walk`, `listdir` and
# `scandir` have NO `Path` method on the floor (`Path.walk` is 3.12+), so they
# are only ever reached as `os.<verb>(...)`, whose receiver RESOLVES through the
# import binding and is already caught by `_IO_MODULES`. Listing them would be
# inert.
#
# ⚠️ `truncate`'s RECEIVER IS A FILE OBJECT, NOT A PATH. `Path.truncate` does not
# exist on any supported version, so a reader checking `dir(Path)` would conclude
# the verb is inert and drop it. `handle.truncate()` is the live shape, and a
# handle held in a parameter is exactly the unresolved receiver this set governs.
#
# ⛔ THE FILESYSTEM PREDICATES ARE NOT TOTAL AND MUST NOT BE REMOVED. An earlier
# reading held that `exists` / `is_file` / `is_dir` "cannot fail" and belonged
# out; that premise is REFUTED and was retracted in livespec v185. `pathlib`
# swallows only `(ENOENT, ENOTDIR, EBADF, ELOOP)` and re-raises everything else,
# so each RAISES `PermissionError` on a path under an unreadable directory. Total
# with respect to four errnos is strictly weaker than total. Pinned by
# `test_the_filesystem_predicates_are_not_removed`.
_UNRESOLVED_RECEIVER_IO_VERBS: frozenset[str] = frozenset(
    {
        "accept",
        "bind",
        "chmod",
        "connect",
        "exists",
        "expanduser",
        "glob",
        "hardlink_to",
        "is_dir",
        "is_fifo",
        "is_file",
        "is_socket",
        "is_symlink",
        "iterdir",
        "listen",
        "lstat",
        "mkdir",
        "open",
        "owner",
        "read",
        "read_bytes",
        "read_text",
        "readline",
        "readlines",
        "readlink",
        "recv",
        "rename",
        "replace",
        "resolve",
        "rglob",
        "rmdir",
        "samefile",
        "sendall",
        "stat",
        "symlink_to",
        "touch",
        "truncate",
        "unlink",
        "urlopen",
        "write",
        "write_bytes",
        "write_text",
        "writelines",
    }
)

# A verb in the set above that names MORE THAN ONE primitive, only one of
# which is I/O, paired with the positional-argument count that identifies the
# I/O one. `replace` is the whole membership today: `Path.replace(target)` is
# an atomic rename, while `str.replace(old, new[, count])` and
# `datetime.replace(**fields)` are pure and vastly commoner.
#
# ⛔ THE `group` REMEDY IS NOT AVAILABLE HERE. `group` was simply dropped from
# the set because no fleet code calls `Path.group()`. Genuine `Path.replace`
# on an UNRESOLVED receiver does exist — `temp_path.replace(path)` in
# livespec's `spec_governance/`, `tmp.replace(path)` in beads-fabro — so
# dropping `replace` would stop detecting three real atomic renames, which is
# a softening. Arity keeps every one of them convicted.
_ARITY_DISCRIMINATED_IO_VERBS: dict[str, int] = {"replace": 1}


def unresolved_receiver_call_is_io(*, call: ast.Call, verb: str) -> bool:
    """Does `<unresolved>.<verb>(...)` reach an I/O boundary?

    The verb decides, except for the handful of verbs that name two unrelated
    primitives; for those the positional-argument count decides, because the
    receiver that would have settled it is exactly what did not resolve.

    ⚠️ DOUBT STILL DISQUALIFIES. `subject.replace(*args)` and
    `subject.replace(**kwargs)` have arity this analysis cannot count, so they
    keep the conservative answer rather than being excused by a count that was
    never taken.
    """
    if verb not in _UNRESOLVED_RECEIVER_IO_VERBS:
        return False
    io_positional_count = _ARITY_DISCRIMINATED_IO_VERBS.get(verb)
    if io_positional_count is None:
        return True
    unknowable = any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    )
    if unknowable:
        return True
    return len(call.args) == io_positional_count and not call.keywords
