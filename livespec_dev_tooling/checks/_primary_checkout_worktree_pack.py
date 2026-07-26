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

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

# The worktree-pack bodies are the SAME single package source the installer
# writes, imported rather than copied so there is no drift seam.
from livespec_dev_tooling.install_worktree_pack import (  # noqa: E402
    CANONICAL_BRANCH_PROTECTION_BODY,
    CANONICAL_BRANCH_PROTECTION_JUST_BODY,
    CANONICAL_WORKTREE_JUST_BODY,
    CANONICAL_WORKTREE_LIB_BODY,
)

__all__: list[str] = [
    "WORKTREE_PACK_DIR_NAME",
    "inspect_worktree_pack",
    "pack_failure_hint",
    "pack_failure_path",
]

# Worktree-pack arm: the installed `dev-tooling/` pack files paired with the
# canonical bodies the `install_worktree_pack` installer writes — the two
# `.sh` scripts plus the two `.just` recipe fragments. The pack is REQUIRED
# by default (A2) — absent entirely it FAILS unless the repo declares
# `"pack": "optional"` or the tree declares the sandbox exemption — and once
# ANY pack file is present ALL MUST be present and byte-identical.
_WORKTREE_PACK_FILES: tuple[tuple[str, str], ...] = (
    ("branch-protection.just", CANONICAL_BRANCH_PROTECTION_JUST_BODY),
    ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY),
    ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY),
    ("worktree.just", CANONICAL_WORKTREE_JUST_BODY),
)
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
_WORKTREE_PACK_REMEDY = (
    "run `just bootstrap` (the `worktree-pack` local obligation row installs "
    "the single canonical `worktree-lib.sh`, `branch-protection.sh`, "
    "`worktree.just`, and `branch-protection.just` bodies byte-for-byte into "
    "`dev-tooling/`); a drifted or partially installed pack is a copy that "
    "diverged from the package source. If `just bootstrap` does not "
    "materialize the pack, this repo is UNWIRED: add the four "
    "`/dev-tooling/*` `.gitignore` entries, both `import?` lines, and the "
    "`install-worktree-pack` recipe, then re-run"
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


def _load_livespec_document(*, repo_root: Path) -> dict[str, object] | None:
    """Return `<repo_root>/.livespec.jsonc` as a dict, or `None` when ungoverned.

    `None` covers all three "this is not a governed repo" shapes: the file is
    absent, it is unreadable JSONC, or its top-level document is not an object.
    An unreadable config is the config-integrity tooling's business, not this
    arm's — failing here would double-report one broken file.
    """
    config_path = repo_root / _LIVESPEC_JSONC_NAME
    if not config_path.is_file():
        return None
    try:
        parsed = jsoncomment.loads(config_path.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def _read_pack_policy(*, repo_root: Path) -> str:
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
    """
    document = _load_livespec_document(repo_root=repo_root)
    if document is None:
        return _PACK_POLICY_UNGOVERNED
    if _WORKTREE_DISCIPLINE_KEY not in document:
        return _PACK_POLICY_REQUIRED
    block = document[_WORKTREE_DISCIPLINE_KEY]
    if not isinstance(block, dict):
        return _PACK_POLICY_MALFORMED
    policy = cast("dict[str, object]", block).get(_PACK_POLICY_KEY, _PACK_POLICY_REQUIRED)
    if policy not in (_PACK_POLICY_REQUIRED, _PACK_POLICY_OPTIONAL):
        return _PACK_POLICY_MALFORMED
    return cast("str", policy)


def _inspect_pack_imports(*, repo_root: Path) -> list[tuple[str, str]]:
    """Return `(fragment_name, failure_mode)` for each un-imported pack fragment.

    A byte-perfect pack whose fragments the root justfile never `import?`s is
    INVISIBLE to `just --list`. That is steps 1-2 of the originating incident's
    causal chain: the session looked for the sanctioned tool, `just --list`
    showed no `worktree-create`, and it fell back to a raw `git worktree add`
    inside the clone. Byte-identity alone cannot see that, so it is asserted
    separately.

    A missing justfile fails both fragments — the pack is equally unreachable
    either way.
    """
    justfile_path = repo_root / _JUSTFILE_NAME
    text = justfile_path.read_text(encoding="utf-8") if justfile_path.is_file() else ""
    return [
        (name, _WORKTREE_PACK_NOT_IMPORTED_FAILURE_MODE)
        for name, import_line in _WORKTREE_PACK_IMPORT_LINES
        if import_line not in text
    ]


def inspect_worktree_pack(
    *, repo_root: Path, sandbox_exempt: bool = False
) -> list[tuple[str, str]]:
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

    Returns the failures sorted by file name for deterministic narration.
    """
    policy = _read_pack_policy(repo_root=repo_root)
    if policy == _PACK_POLICY_MALFORMED:
        return [(_LIVESPEC_JSONC_NAME, _WORKTREE_DISCIPLINE_MALFORMED_FAILURE_MODE)]
    pack_dir = repo_root / WORKTREE_PACK_DIR_NAME
    any_present = any((pack_dir / name).is_file() for name, _ in _WORKTREE_PACK_FILES)
    if not any_present:
        if policy == _PACK_POLICY_REQUIRED and not sandbox_exempt:
            return [(WORKTREE_PACK_DIR_NAME, _WORKTREE_PACK_ABSENT_FAILURE_MODE)]
        return []
    failures: list[tuple[str, str]] = []
    for name, canonical_body in _WORKTREE_PACK_FILES:
        script_path = pack_dir / name
        if not script_path.is_file():
            failures.append((name, _WORKTREE_PACK_MISSING_FAILURE_MODE))
            continue
        if script_path.read_text(encoding="utf-8") != canonical_body:
            failures.append((name, _WORKTREE_PACK_BODY_MISMATCH_FAILURE_MODE))
    failures.extend(_inspect_pack_imports(repo_root=repo_root))
    return sorted(failures)


def pack_failure_hint(*, failure_mode: str) -> str:
    """Return the remedy string for one pack failure mode.

    Routing exists because the modes are actionable in three different places
    — the config, the root justfile, and the pack itself — so one shared
    remedy string would misdirect the operator two thirds of the time.
    """
    return _PACK_REMEDIES.get(failure_mode, _WORKTREE_PACK_REMEDY)
