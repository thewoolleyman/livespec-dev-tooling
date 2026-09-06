"""_primary_checkout_hook_files — the hook byte-identity and vendored-copy arms.

Private sibling of `primary_checkout_commit_refuse_hook_installed`, split out
for the same reason `_primary_checkout_git_probes` and
`_primary_checkout_worktree_pack` were: the parent crossed its 250-LLOC hard
ceiling, this time because putting the file reads on the railway added a
failure branch and its narration. The leading underscore marks it a helper,
not a check entry point — it ships no `main` and is never invoked as a check
slug, so `check-aggregate-completeness` stays untouched across the fleet.

⛔ THE MOVE IS NOT WHY THESE TWO CHANGED. The extraction forced the question
the epic asks of every function, and the answer convicted the check's most
important arm: `inspect_hook` compared DECODED TEXT while the parent's
docstring promised "STRICT BYTE-IDENTITY (zs22.7.9.5)". `Path.read_text`
performs universal-newline translation, so a CRLF-converted hook — bytes
plainly different from `CANONICAL_HOOK_BODY` — decoded back to the canonical
string and this arm returned `(True, "")`. The MANDATORY arm of the check, on
its own central assertion, reporting a hook it had not verified. Measured, not
reasoned. The decode was also the only reason a hook whose bytes are not valid
UTF-8 raised `UnicodeDecodeError` out of the check instead of reporting the
`body_mismatch` that was always available: the canonical body is UTF-8 by
construction, so bytes that do not decode cannot equal it.

Output discipline: this module computes; the parent narrates.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.

# The canonical body is the SINGLE source of truth, shipped as a module
# constant in the installer so it travels in the wheel. This module imports it
# (rather than carrying a second copy) so byte-identity is verified against
# the exact bytes the installer writes — there is no drift seam.
# ABSOLUTE, deliberately, where the other sibling imports are bare. A bare
# import creates a SECOND module object under `python3 <path>` invocation, and
# with it a second `CheckInputUnreadable` class — so a failure raised here
# would not compare equal to one the caller matched on. Measured: the unit
# tests' equality assertions failed on exactly that.
from livespec_dev_tooling.checks._primary_checkout_unreadable import (  # noqa: E402
    CheckInputUnreadable,
)
from livespec_dev_tooling.install_commit_refuse_hooks import (  # noqa: E402
    CANONICAL_HOOK_BODY,
    _is_foreign_lefthook_wrapper,
)

# Both names keep the leading underscore they had in the parent, and are
# re-exported through `__all__` (which pyright honours for
# `reportUnusedFunction`). Renaming them public to satisfy the extraction would
# enrol two functions in the railway universe as brand-new offenders — the
# split reporting work it did not do. They are converted anyway, because the
# defect below is real whether or not the count can see it.
__all__: list[str] = [
    "_find_foreign_lefthook_wrappers",
    "_find_vendored_hook_copies",
    "_inspect_hook",
]

# No-vendored-copy arm: a shell copy of the hook source under either of
# these names is a drift seam (the package constant is the single source).
_VENDORED_COPY_NAMES: tuple[str, ...] = (
    "git-hook-wrapper.sh",
    "livespec-commit-refuse-hook.sh",
)

# Path components carved out of the no-vendored-copy scan. `templates/` is
# the template-source domain (zs22.7.9.3 ships a hook copy there as a
# template artifact, not an installed/vendored copy); `.git/` is git's own
# internal tree (the installed hooks live there under their own names).
_VENDORED_COPY_CARVE_OUT_PARTS: frozenset[str] = frozenset({"templates", ".git"})

_HOOK_MISSING = "missing"
_HOOK_NOT_EXECUTABLE = "not_executable"
_HOOK_BODY_MISMATCH = "body_mismatch"
_HOOK_OK = ""


def _inspect_hook(*, hook_path: Path) -> IOResult[tuple[bool, str], CheckInputUnreadable]:
    """Return `(ok, failure_mode)` for a single hook path.

    `ok` is True only when the hook exists as a regular file, is
    executable by the current user, and its body is BYTE-IDENTICAL to
    `CANONICAL_HOOK_BODY`. `failure_mode` is one of:

    - `"missing"` — the hook file is absent or is not a regular file.
    - `"not_executable"` — the hook exists but the executable bit is
      unset for the current user (`os.access(path, os.X_OK)`).
    - `"body_mismatch"` — the hook is executable but its bytes differ
      from `CANONICAL_HOOK_BODY` (covers the empty-file case, a body that
      would have passed the retired loose fingerprint, a CRLF-converted
      copy, and bytes that are not valid UTF-8 at all).
    - `""` (empty string) — the hook is correct; paired with `ok=True`.

    All four are ANSWERS and ride the success track. The failure track
    carries only a read that did not happen, which is a fact about this run
    rather than about the hook — and reporting it as `missing` or
    `body_mismatch` would send the operator to reinstall a hook whose state
    this run never observed.

    The comparison is on BYTES. It previously decoded, which made a
    CRLF-converted hook compare EQUAL to canonical and pass.
    """
    if not hook_path.is_file():
        return IOSuccess((False, _HOOK_MISSING))
    if not os.access(hook_path, os.X_OK):
        return IOSuccess((False, _HOOK_NOT_EXECUTABLE))
    try:
        body = hook_path.read_bytes()
    except OSError as unreadable:
        return IOFailure(CheckInputUnreadable(path=str(hook_path), detail=str(unreadable)))
    if body != CANONICAL_HOOK_BODY.encode("utf-8"):
        return IOSuccess((False, _HOOK_BODY_MISMATCH))
    return IOSuccess((True, _HOOK_OK))


def _find_foreign_lefthook_wrappers(
    *, hooks_dir: Path
) -> IOResult[list[Path], CheckInputUnreadable]:
    """Every hooks-dir executable that reaches lefthook without the canonical unset line.

    THE ARM THE OBSERVED DEFECT NEEDED. The byte-identity arm above inspects
    exactly the three names the installer writes, so a FOURTH file in the same
    directory was invisible to this check entirely — and on 2026-09-06
    `/data/projects/livespec/.git/hooks/prepare-commit-msg` was exactly that: a
    stock lefthook `call_lefthook` wrapper with an mtime three months older
    than its canonical siblings, firing on every commit and every cherry-pick,
    leaking GIT_DIR, and calling `lefthook run` without `--no-auto-install`.
    Three green byte-identity verdicts said nothing about it.

    The predicate is imported from the installer rather than restated here, for
    the same reason `CANONICAL_HOOK_BODY` is: the installer is the component
    that must REMOVE this shape, and a verifier carrying its own copy of "what
    the shape is" would drift into failing on files the installer does not
    clear, or passing files it does.

    The canonical three carry the unset line by construction and so never
    match, which is what lets this arm scan the WHOLE directory by shape
    instead of carving three names out of it.

    An absent hooks directory yields an EMPTY list rather than a read failure:
    the byte-identity arm already reports that state as three `missing` hooks,
    and spelling it `hook_unreadable` here would hand the operator a remedy for
    an access fault that never happened.
    """
    if not hooks_dir.is_dir():
        return IOSuccess([])
    try:
        entries = sorted(hooks_dir.iterdir())
    except OSError as unreadable:
        return IOFailure(CheckInputUnreadable(path=str(hooks_dir), detail=str(unreadable)))
    found: list[Path] = []
    for candidate in entries:
        try:
            is_wrapper = _is_foreign_lefthook_wrapper(path=candidate)
        except OSError as unreadable:
            return IOFailure(CheckInputUnreadable(path=str(candidate), detail=str(unreadable)))
        if is_wrapper:
            found.append(candidate)
    return IOSuccess(found)


def _find_vendored_hook_copies(*, repo_root: Path) -> IOResult[list[Path], CheckInputUnreadable]:
    """Return every vendored hook-source copy under `repo_root`, sorted.

    Scans the work-tree root for files named `git-hook-wrapper.sh` or
    `livespec-commit-refuse-hook.sh`, EXCLUDING any path with a component
    under the `templates/` or `.git/` carve-outs. A match outside the
    carve-outs is a drift seam (a second source of the hook body) and a
    FAIL. An empty list means the scan COMPLETED and found nothing.

    That last sentence is why this returns a `Result` at all. `rglob` walks
    the whole work tree and can raise part-way through, and the empty list it
    would otherwise unwind to is indistinguishable from a clean scan — a
    silent pass on an arm whose entire job is to find a file that should not
    be there.
    """
    found: list[Path] = []
    try:
        for name in _VENDORED_COPY_NAMES:
            for candidate in repo_root.rglob(name):
                relative_parts = candidate.relative_to(repo_root).parts
                if any(part in _VENDORED_COPY_CARVE_OUT_PARTS for part in relative_parts):
                    continue
                found.append(candidate)
    except OSError as unreadable:
        return IOFailure(CheckInputUnreadable(path=str(repo_root), detail=str(unreadable)))
    return IOSuccess(sorted(found))
