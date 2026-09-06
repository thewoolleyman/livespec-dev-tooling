"""_primary_checkout_worktree_pack — the worktree-discipline PACK arm.

Private sibling of `primary_checkout_commit_refuse_hook_installed`, split out
for the same reason `_primary_checkout_git_probes` was: the parent module
crossed its 250-LLOC hard ceiling. The leading underscore marks it a helper,
not a check entry point — it ships no `main` and is never invoked as a check
slug, so `check-aggregate-completeness` stays untouched across the fleet.

WHAT THIS ARM ENFORCES (zs22 A2). The pack is REQUIRED BY DEFAULT: an absent
`worktree_discipline` key in `.livespec.jsonc` MEANS `required`. That is a
deliberate divergence from the `harnesses` precedent in
`checks/plugin_resolution.py`, where an absent key is itself fail-closed.
Here the default is a POLICY, so a repo satisfying `required` passes with no
key at all and only a repo that fails it is failed; copying the precedent's
shape would red every conformant fleet repo instead.

Beyond byte-identity the arm asserts DISCOVERABILITY: a byte-perfect pack
whose fragments the root justfile never `import?`s is invisible to
`just --list`. That is steps 1-2 of the originating incident's causal chain,
and byte-comparison alone cannot see it.

Output discipline: this module computes; the parent narrates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware.

# The worktree-pack bodies are the SAME single package source the installer
# writes, imported rather than copied so there is no drift seam.
# ABSOLUTE, deliberately, where the other sibling imports are bare. A bare
# import creates a SECOND module object under `python3 <path>` invocation, and
# with it a second `CheckInputUnreadable` class — so a failure raised here
# would not compare equal to one the caller matched on. Measured: the unit
# tests' equality assertions failed on exactly that.
from livespec_dev_tooling.checks._primary_checkout_unreadable import (  # noqa: E402
    CheckInputUnreadable,
)
from livespec_dev_tooling.install_worktree_pack import (  # noqa: E402
    WORKTREE_PACK_FILES,
)

__all__: list[str] = [
    "WORKTREE_PACK_DIR_NAME",
    "inspect_worktree_pack",
    "pack_failure_hint",
    "pack_failure_path",
]


# Worktree-pack arm: this arm walks `WORKTREE_PACK_FILES`, the installer's
# SINGLE enumeration of the pack — the four `.sh` scripts, the two `.just`
# recipe fragments, and the generated `.gitignore` — rather than a hand-written
# copy of the set. The copy is what this arm used to carry, and it drifted:
# measured 2026-09-06 it asserted six files where the `worktree-pack` bootstrap
# obligation row asserted four, so `just bootstrap` passed a pack this gate
# rejected (livespec-dev-tooling-l5gypl). The pack is REQUIRED by default (A2)
# — absent entirely it FAILS unless the repo declares `"pack": "optional"` or
# the tree declares the sandbox exemption — and once ANY pack file is present
# ALL MUST be present and byte-identical.
WORKTREE_PACK_DIR_NAME = "dev-tooling"
_WORKTREE_PACK_BODY_MISMATCH_FAILURE_MODE = "worktree_pack_body_mismatch"
_WORKTREE_PACK_MISSING_FAILURE_MODE = "worktree_pack_file_missing"
_WORKTREE_PACK_ABSENT_FAILURE_MODE = "worktree_pack_absent"
_WORKTREE_PACK_NOT_IMPORTED_FAILURE_MODE = "worktree_pack_not_imported"
_WORKTREE_DISCIPLINE_MALFORMED_FAILURE_MODE = "worktree_discipline_malformed"

# The remedy names `just bootstrap` FIRST, not `just install-worktree-pack`.
# `bootstrap` exists in every governed repo and reaches the pack through the
# `worktree-pack` LOCAL obligation row; the standalone recipe exists only in
# repos that have already been wired, so naming it first would emit a remedy
# that fails in exactly the repos the failure fires in.
#
# The file list is RENDERED from the installer's enumeration rather than typed
# out. A remedy naming a stale set is the same drift the arm itself carried,
# and it is worse where an operator reads it: it tells them a pack is complete
# when it is a member short.
_WORKTREE_PACK_FILE_LIST = ", ".join(f"`{pack_file.name}`" for pack_file in WORKTREE_PACK_FILES)
_WORKTREE_PACK_REMEDY = (
    "run `just bootstrap` (the `worktree-pack` local obligation row installs "
    f"the single canonical {_WORKTREE_PACK_FILE_LIST} bodies byte-for-byte "
    "into `dev-tooling/`); a drifted or partially installed pack is a copy "
    "that diverged from the package source. If `just bootstrap` does not "
    "materialize the pack, this repo is UNWIRED: add both `import?` lines and "
    "the `install-worktree-pack` recipe, then re-run"
)
_WORKTREE_PACK_NOT_IMPORTED_REMEDY = (
    "add the missing optional import to the root justfile — `import? "
    "'dev-tooling/worktree.just'` and `import? "
    "'dev-tooling/branch-protection.just'`. The pack bytes are correct but "
    "unreachable: without the import the `worktree-*` recipes never appear in "
    "`just --list`, which is how a session finds the sanctioned tool"
)
_WORKTREE_DISCIPLINE_MALFORMED_REMEDY = (
    "fix the `worktree_discipline` block in `.livespec.jsonc`: it MUST be an "
    'object whose `pack` key is either "required" (the default when the key '
    'is absent) or "optional" (the declared, reviewable opt-out)'
)

# Config gate for the pack arm. `worktree_discipline.pack` is read from the
# consumer's `.livespec.jsonc`; an ABSENT key means `required`. This
# DELIBERATELY diverges from the `harnesses` precedent in
# `checks/plugin_resolution.py`, where an absent key is itself fail-closed:
# here the default is a POLICY, so a repo that satisfies `required` passes
# with no key at all, and only a repo that fails it is failed.
_LIVESPEC_JSONC_NAME = ".livespec.jsonc"
_WORKTREE_DISCIPLINE_KEY = "worktree_discipline"
_PACK_POLICY_KEY = "pack"
_PACK_POLICY_REQUIRED = "required"
_PACK_POLICY_OPTIONAL = "optional"
_PACK_POLICY_UNGOVERNED = "ungoverned"
_PACK_POLICY_MALFORMED = "malformed"
_JUSTFILE_NAME = "justfile"
# The two `import?` lines the pack's discoverability depends on, paired with
# the fragment each makes reachable.
_WORKTREE_PACK_IMPORT_LINES: tuple[tuple[str, str], ...] = (
    ("branch-protection.just", "import? 'dev-tooling/branch-protection.just'"),
    ("worktree.just", "import? 'dev-tooling/worktree.just'"),
)


# Per-failure-mode remedy routing. The three new modes are actionable in
# different places — config, justfile, and the pack itself — so a single
# remedy string would misdirect two thirds of the time.
_PACK_REMEDIES: dict[str, str] = {
    _WORKTREE_DISCIPLINE_MALFORMED_FAILURE_MODE: _WORKTREE_DISCIPLINE_MALFORMED_REMEDY,
    _WORKTREE_PACK_NOT_IMPORTED_FAILURE_MODE: _WORKTREE_PACK_NOT_IMPORTED_REMEDY,
}


def pack_failure_path(*, repo_root: Path, script_name: str) -> Path:
    """Resolve the reported path for one pack failure.

    File-scoped failures point at the offending pack file. The two
    repo-scoped modes point at what the operator must actually edit: the
    `.livespec.jsonc` for a malformed block, and the `dev-tooling/` directory
    for an absent pack.
    """
    if script_name in (_LIVESPEC_JSONC_NAME, WORKTREE_PACK_DIR_NAME):
        return repo_root / script_name
    return repo_root / WORKTREE_PACK_DIR_NAME / script_name


def _read_bytes(*, path: Path) -> IOResult[bytes, CheckInputUnreadable]:
    """Read `path`'s bytes, or name the read that did not happen.

    The single read seam for all three of this arm's inputs — the config, the
    pack files and the root justfile. Bytes rather than text because none of
    the three questions this arm asks needs a decoded string, and decoding was
    what previously turned answerable states into crashes.

    Callers reach here only past an `is_file()` probe, which is what keeps an
    ABSENT file — a definitive fact, and for the config a load-bearing one —
    off this failure track entirely.
    """
    try:
        return IOSuccess(path.read_bytes())
    except OSError as unreadable:
        return IOFailure(CheckInputUnreadable(path=str(path), detail=str(unreadable)))


def _load_livespec_document(
    *, repo_root: Path
) -> IOResult[dict[str, object] | None, CheckInputUnreadable]:
    """Return `<repo_root>/.livespec.jsonc` as a dict, or `None` when ungoverned.

    `None` covers the three DEFINITIVE "this is not a governed repo" shapes:
    the file is absent, its bytes are not a parseable JSONC document, or its
    top-level document is not an object. A broken config is the
    config-integrity tooling's business, not this arm's — failing here would
    double-report one broken file.

    ⛔ A FOURTH SHAPE USED TO HIDE AMONG THEM: the read never happening. That
    is not a fact about the repository, and returning `None` for it made an
    unread config indistinguishable from an ABSENT one — so a governed repo
    whose config could not be read was reported as needing no pack. It now
    leaves on the failure track.

    ⚠️ The UTF-8 decode is caught EXPLICITLY. It was previously swallowed only
    because `UnicodeDecodeError` happens to subclass `ValueError` — the right
    outcome by an accident of the exception hierarchy rather than by a
    decision anyone could review. It IS the right outcome: JSON is defined
    over UTF-8, so bytes that do not decode are definitively not a parseable
    document, exactly like the invalid-JSON case beside it.
    """
    config_path = repo_root / _LIVESPEC_JSONC_NAME
    if not config_path.is_file():
        return IOSuccess(None)
    raw = _read_bytes(path=config_path)
    if isinstance(raw, IOFailure):
        return raw
    try:
        parsed = jsoncomment.loads(unsafe_perform_io(raw.unwrap()).decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return IOSuccess(None)
    return IOSuccess(cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None)


def _read_pack_policy(*, repo_root: Path) -> IOResult[str, CheckInputUnreadable]:
    """Return the effective `worktree_discipline.pack` policy for `repo_root`.

    One of `_PACK_POLICY_REQUIRED` / `_PACK_POLICY_OPTIONAL` /
    `_PACK_POLICY_UNGOVERNED` / `_PACK_POLICY_MALFORMED`.

    `.livespec.jsonc` ABSENT (or unreadable, or not a JSON object) →
    `_PACK_POLICY_UNGOVERNED`. This is a STATED choice, not one inherited from
    `plugin_resolution`'s skip arm: that file is what makes a directory
    governed, so the pack arm cannot be more governed-aware than the file
    defining governance, and this check also runs in throwaway directories.
    It is deliberately not a usable opt-out — deleting `.livespec.jsonc` from a
    real fleet repo strips `template` / `spec_root` / `harnesses` / `compat`
    and reds fleet conformance loudly, trading a silent gap for an unmissable
    one.

    A present-but-garbled block is `_PACK_POLICY_MALFORMED` (fail-closed,
    matching the `harnesses` precedent), and an ABSENT key is
    `_PACK_POLICY_REQUIRED` — the flip this check exists for.

    ⛔ `_PACK_POLICY_UNGOVERNED` is a CLAIM — "this directory is not a livespec
    repo" — and it is the most consequential value here, because an ungoverned
    tree needs no pack and the arm returns clean. It is now reachable only
    from evidence: the config absent, or present and definitively unparseable.
    A read that did not happen no longer reaches it.
    """
    loaded = _load_livespec_document(repo_root=repo_root)
    if isinstance(loaded, IOFailure):
        return loaded
    document = unsafe_perform_io(loaded.unwrap())
    if document is None:
        return IOSuccess(_PACK_POLICY_UNGOVERNED)
    if _WORKTREE_DISCIPLINE_KEY not in document:
        return IOSuccess(_PACK_POLICY_REQUIRED)
    block = document[_WORKTREE_DISCIPLINE_KEY]
    if not isinstance(block, dict):
        return IOSuccess(_PACK_POLICY_MALFORMED)
    policy = cast("dict[str, object]", block).get(_PACK_POLICY_KEY, _PACK_POLICY_REQUIRED)
    if policy not in (_PACK_POLICY_REQUIRED, _PACK_POLICY_OPTIONAL):
        return IOSuccess(_PACK_POLICY_MALFORMED)
    return IOSuccess(cast("str", policy))


def _inspect_pack_imports(
    *, repo_root: Path
) -> IOResult[list[tuple[str, str]], CheckInputUnreadable]:
    """Return `(fragment_name, failure_mode)` for each un-imported pack fragment.

    A byte-perfect pack whose fragments the root justfile never `import?`s is
    INVISIBLE to `just --list`. That is steps 1-2 of the originating incident's
    causal chain: the session looked for the sanctioned tool, `just --list`
    showed no `worktree-create`, and it fell back to a raw `git worktree add`
    inside the clone. Byte-identity alone cannot see that, so it is asserted
    separately.

    A missing justfile fails both fragments — the pack is equally unreachable
    either way.

    The justfile is searched as BYTES, never decoded. Both `import?` lines are
    pure ASCII, so "does this file contain this line" is answerable without
    interpreting the rest of the file — and an undecodable justfile used to
    raise `UnicodeDecodeError` straight out of the check rather than answer a
    question it could answer. A justfile `just` itself cannot read is exactly
    the state this arm exists to report.
    """
    justfile_path = repo_root / _JUSTFILE_NAME
    if not justfile_path.is_file():
        return IOSuccess(
            [
                (name, _WORKTREE_PACK_NOT_IMPORTED_FAILURE_MODE)
                for name, _ in _WORKTREE_PACK_IMPORT_LINES
            ]
        )
    read = _read_bytes(path=justfile_path)
    if isinstance(read, IOFailure):
        return read
    raw = unsafe_perform_io(read.unwrap())
    return IOSuccess(
        [
            (name, _WORKTREE_PACK_NOT_IMPORTED_FAILURE_MODE)
            for name, import_line in _WORKTREE_PACK_IMPORT_LINES
            if import_line.encode("utf-8") not in raw
        ]
    )


def _inspect_pack_bodies(
    *, pack_dir: Path
) -> IOResult[list[tuple[str, str]], CheckInputUnreadable]:
    """Compare each present pack file's BYTES against its canonical body.

    A sibling absent while the pack is otherwise present is a partial or
    drifted install, which is a fact about the pack; a sibling present whose
    read fails is not, and only the second leaves the success track.
    """
    failures: list[tuple[str, str]] = []
    for pack_file in WORKTREE_PACK_FILES:
        script_path = pack_dir / pack_file.name
        if not script_path.is_file():
            failures.append((pack_file.name, _WORKTREE_PACK_MISSING_FAILURE_MODE))
            continue
        read = _read_bytes(path=script_path)
        if isinstance(read, IOFailure):
            return read
        if unsafe_perform_io(read.unwrap()) != pack_file.body.encode("utf-8"):
            failures.append((pack_file.name, _WORKTREE_PACK_BODY_MISMATCH_FAILURE_MODE))
    return IOSuccess(failures)


def inspect_worktree_pack(
    *, repo_root: Path, sandbox_exempt: bool = False
) -> IOResult[list[tuple[str, str]], CheckInputUnreadable]:
    """Return `(file_name, failure_mode)` tuples for worktree-pack violations.

    The pack is REQUIRED BY DEFAULT (zs22 A2). Absence of the
    `worktree_discipline` key in `.livespec.jsonc` means `required`, so a
    governed repo carrying no pack is a FAIL — the fail-open this arm used to
    have, and the one the originating incident fell through. A repo may still
    decline the pack, but only by DECLARING `"pack": "optional"` in tracked
    config where a reviewer sees it.

    `sandbox_exempt` is the caller's reading of the DECLARED
    `livespec.sandboxExempt` git-config marker, and it suppresses the PRESENCE
    arm only. The pack is gitignored by design, so it exists only after
    `just bootstrap`; a Fabro sandbox is a fresh full clone that runs this
    check as a SETUP step BEFORE bootstrap, where pack presence is not a
    property that can hold. Requiring it there is a false positive, and it took
    every dispatch in `livespec-orchestrator-beads-fabro` down. This reuses the
    same marker `CANONICAL_HOOK_BODY` already honours in its refuse-at-primary
    and positive-location arms — the Exemption slot of the Conformance
    Pattern's concern #1 Worktree-discipline — rather than inventing a second
    opt-out.

    It defaults to False (fail-closed, the pre-fix behaviour) so a caller that
    forgets to wire it loses the exemption rather than the enforcement. The
    wiring itself is proven end-to-end by the parent check's subprocess tests,
    which set the real git config in a real repo — a direct call here cannot
    show that `main()` reads the marker at all.

    - governed, `required`, no pack at all → `worktree_pack_absent`;
    - `required` but the tree DECLARES the sandbox exemption, no pack → skip;
    - `optional` (or ungoverned), no pack at all → skip;
    - garbled `worktree_discipline` block → `worktree_discipline_malformed`;
    - a present file whose bytes differ → `worktree_pack_body_mismatch`;
    - a sibling absent while the pack is otherwise present →
      `worktree_pack_file_missing` (a partial/drifted install);
    - a present pack whose fragments are not `import?`ed →
      `worktree_pack_not_imported`.

    The byte-identity arms run whenever a pack is present, INDEPENDENT of
    policy AND of the sandbox exemption: an installed pack must be canonical
    even in a repo that declared the pack optional, carries no config at all,
    or is an exempt sandbox. Exempting drift too would retire the very
    detection this arm exists for.

    ⛔ AND THEY COMPARE BYTES, which they previously only claimed to do. The
    comparison read DECODED TEXT, and `Path.read_text` performs
    universal-newline translation — so a CRLF-converted pack file decoded back
    to the canonical string and this arm reported the pack CLEAN while the
    bytes on disk differed from the ones the installer wrote. That is this
    arm's own central assertion failing open. The decode was also the only
    reason an undecodable pack file raised out of the check: the canonical
    bodies are UTF-8 by construction, so bytes that do not decode cannot equal
    them, and a `worktree_pack_body_mismatch` was always available.

    Returns the failures sorted by file name for deterministic narration —
    on the SUCCESS track, which is where every condition above lives. The
    failure track carries one thing only: a file this arm needed to read that
    did not answer, which is a fact about this run rather than about the pack.
    """
    policy_read = _read_pack_policy(repo_root=repo_root)
    if isinstance(policy_read, IOFailure):
        return policy_read
    policy = unsafe_perform_io(policy_read.unwrap())
    if policy == _PACK_POLICY_MALFORMED:
        return IOSuccess([(_LIVESPEC_JSONC_NAME, _WORKTREE_DISCIPLINE_MALFORMED_FAILURE_MODE)])
    pack_dir = repo_root / WORKTREE_PACK_DIR_NAME
    if not any((pack_dir / pack_file.name).is_file() for pack_file in WORKTREE_PACK_FILES):
        required = policy == _PACK_POLICY_REQUIRED and not sandbox_exempt
        absent = [(WORKTREE_PACK_DIR_NAME, _WORKTREE_PACK_ABSENT_FAILURE_MODE)]
        return IOSuccess(absent if required else [])
    bodies = _inspect_pack_bodies(pack_dir=pack_dir)
    if isinstance(bodies, IOFailure):
        return bodies
    imports = _inspect_pack_imports(repo_root=repo_root)
    if isinstance(imports, IOFailure):
        return imports
    return IOSuccess(
        sorted([*unsafe_perform_io(bodies.unwrap()), *unsafe_perform_io(imports.unwrap())])
    )


def pack_failure_hint(*, failure_mode: str) -> str:
    """Return the remedy string for one pack failure mode.

    Routing exists because the modes are actionable in three different places
    — the config, the root justfile, and the pack itself — so one shared
    remedy string would misdirect the operator two thirds of the time.
    """
    return _PACK_REMEDIES.get(failure_mode, _WORKTREE_PACK_REMEDY)
