"""shipped_path_release_guard_core — pure decisions for the shipped-path release guard.

WHY THE GUARD EXISTS. A change typed `docs(...)` — or any other type its
repository does not release on — to a path a PLUGIN SHIPS cuts no release, so
the edited bytes reach ZERO running seats while `just ensure-plugins` reports
"already current": that command compares PINS, not served bytes. Nothing
mechanical catches the gap, which is what the guard this module decides for is
being built to close.

This module is the DECISION CORE and nothing else. Every function here is
PURE — no git, no filesystem, no subprocess, no environment, no clock. The
changed paths, the commit subject and body, the repo's releasing-type set, the
shipped-path prefixes and the override all arrive as ARGUMENTS. RESOLVING them
from a real repository (its release-please config, its plugin manifests, its
staged diff) belongs to the runnable check that wraps this core, so that the
rule can be tested exhaustively without a repository and so that one rule has
exactly one implementation.

THE RELEASING SET IS PER-REPO AND IS AN INPUT — see `commit_releases`, which
carries the evidence for why it can never be a constant here.

AGREEMENT WITH `workflow_checks/release_bump_classification.py`. That module
models the same commit types for a different question (is the DECLARED semver
bump weaker than the surface delta requires), and treats `fix` and `perf` as
patch types — i.e. `perf` RELEASES. Two modules in one package must not model
one type's release behaviour in opposite directions, so the subject grammar
below is deliberately the same grammar, and a test in this module's beside-test
pins the two together on `perf`. The grammar is restated rather than imported
because that module reaches `git` and this one must stay pure; if a third
consumer ever appears, promote the grammar to a shared pure module rather than
adding a third copy.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "commit_releases",
    "is_violation",
    "touches_shipped_path",
]

# Conventional-Commit subject prefix: `type(scope)!: subject`. The `!` group is
# the breaking marker; scope is optional and its contents are not inspected.
# Same grammar as `release_bump_classification._SUBJECT_PREFIX`, deliberately.
_SUBJECT_PREFIX = re.compile(r"^(?P<type>[a-zA-Z]+)(?P<scope>\([^)]*\))?(?P<bang>!)?:")
# Both spellings release-please honours, anchored per line because a footer is
# its own line in the commit body.
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def commit_releases(*, subject: str, body: str, releasing_types: frozenset[str]) -> bool:
    """Report whether this commit's type cuts a release in the repo that supplied the set.

    A subject whose type is not a Conventional Commit at all cuts no release,
    which is an ANSWER rather than a parse failure: release-please types what it
    can and ignores what it cannot, so an untypeable subject genuinely carries
    no bump.
    """
    # THE RELEASING SET IS AN INPUT, DERIVED PER REPO FROM THAT REPO'S
    # release-please `changelog-sections` (the `hidden: false` entries) — NEVER
    # hardcoded here, and never re-derived from doctrine.
    #
    # MEASURED, because the doctrine is WRONG and a reader who trusts it will
    # rebuild the refuted set. livespec's AGENTS.md says "refactor:/perf:
    # commits cut no release"; livespec's own release history says otherwise.
    # The range v0.28.2..v0.28.3 held 36 commits — 5 `refactor`, 5 `chore`, 26
    # `docs`, and ZERO `feat`, `fix`, `revert` or breaking markers — and
    # v0.28.3 WAS CUT. The v0.21.3 range's only non-`docs` commit was a single
    # `revert` with no breaking footer, and a release was cut there too. The
    # negative control is the docs-and-chore-only window of 2026-08-30 to
    # 2026-09-08: 30+ commits, no release. So on livespec's config the
    # empirical releasing set IS its `hidden: false` set, and deriving it from
    # `changelog-sections` gives the right answer.
    #
    # AND IT IS GENUINELY PER-REPO, which is the other half of why it is a
    # parameter: release-please's DEFAULT sections hide `refactor`, so a repo
    # declaring no `changelog-sections` does NOT release on `refactor` while
    # livespec (which declares them) does. One constant could only be wrong for
    # one of those two repos.
    if _BREAKING_FOOTER.search(body):
        return True
    match = _SUBJECT_PREFIX.match(subject)
    if match is None:
        return False
    if match.group("bang"):
        return True
    return match.group("type").lower() in releasing_types


def touches_shipped_path(
    *, changed_paths: tuple[str, ...], shipped_prefixes: frozenset[str]
) -> bool:
    """Report whether any changed path falls under any shipped prefix.

    A prefix matches a path it EQUALS (a shipped file named exactly) and any
    path beneath it at a path-SEGMENT boundary. The boundary is what keeps
    `livespec/SPECIFICATION-notes.md` from matching the prefix
    `livespec/SPECIFICATION`; a trailing slash on a supplied prefix is
    normalized away so both spellings of a directory behave identically.
    """
    return any(
        _under_prefix(path=path, prefix=prefix)
        for path in changed_paths
        for prefix in shipped_prefixes
    )


def _under_prefix(*, path: str, prefix: str) -> bool:
    """Report whether `path` equals `prefix` or sits beneath it at a segment boundary."""
    directory = prefix.rstrip("/")
    return path == directory or path.startswith(f"{directory}/")


def is_violation(
    *,
    subject: str,
    body: str,
    changed_paths: tuple[str, ...],
    shipped_prefixes: frozenset[str],
    releasing_types: frozenset[str],
    override: bool,
) -> bool:
    """Report whether this change edits shipped bytes that no release will carry.

    True exactly when the change intersects the shipped set AND its commit type
    does not release AND no override was passed. The override is an INPUT here:
    what an operator must do to obtain one — where it is written, what it must
    say, who may write it — belongs to the runnable check, so that this core
    stays a decision rather than a policy.
    """
    if override:
        return False
    if not touches_shipped_path(changed_paths=changed_paths, shipped_prefixes=shipped_prefixes):
        return False
    return not commit_releases(subject=subject, body=body, releasing_types=releasing_types)
