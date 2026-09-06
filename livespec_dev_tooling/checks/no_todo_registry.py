"""no_todo_registry — `tests/heading-coverage.json` TODO entries, gated by OWNERSHIP.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-todo-registry` row), a `test: "TODO"`
entry is an authoring placeholder rather than real coverage.

ENTRY SCHEMA — the `work_item` field. A heading-coverage entry
using `test: "TODO"` MUST also carry a non-empty string
`work_item` naming the covering-test work-item that owns
replacing it, stamped beside `reason`. Per livespec core's
`SPECIFICATION/spec.md` (the heading-coverage co-edit rule) the
revise flow files that item and stamps the returned id; where a
project has no configured orchestrator the author supplies an
id from the project's own tracker. "An unowned TODO entry is
never valid." An entry whose `work_item` is absent, empty,
whitespace-only, or not a string is UNOWNED.

The TODO scan ALWAYS runs (no skip carve-out, no exemption list,
no per-repo opt-in). A self-documenting severity lever selects
between two tiers:

- PER-COMMIT tier (lever unset or empty): every TODO entry is
  logged at WARNING level and the check exits 0, so authoring
  placeholders surface without blocking `just check`. Ownership
  does NOT change this tier's verdict.
- RELEASE tier (`LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST`
  set to a non-empty value; CI sets it for the release context):
  per `SPECIFICATION/non-functional-requirements.md`
  § "Release-gate targets", the tier rejects an UNOWNED TODO
  and, where the configured tracker makes liveness mechanically
  checkable, one whose named `work_item` is closed or
  nonexistent. An owned live TODO does not block an unrelated
  release.

The release tier is therefore strictly NARROWER than the
per-commit tier's finding set — unowned is a subset of any — so
narrowing it can only stop reddening repos, never start.

STAGED-DIFF SCOPE (`LIVESPEC_SCOPE_HEADING_COVERAGE_TODOS_TO_HEAD_DIFF`
set to a non-empty value) narrows the ARMED tier's VERDICT to the
entries a commit is actually authoring: those that differ from
`HEAD:tests/heading-coverage.json`, added or modified. The lever is
inert unless the release lever is also set — it selects WHICH entries
the armed tier judges, never WHETHER the scan runs.

The `after` side of that comparison is the WORKING-TREE copy this check
already loads, not the index, so an unstaged registry edit counts as in
scope too. That is deliberate and it is the fail-closed direction — the
judged set is a SUPERSET of the staged diff, never a subset — and it is
why the lever is named for `HEAD` rather than for the index.

It exists because arming over the whole registry made
`tests/heading-coverage.json` UNWRITABLE. The doc-only pre-commit
(`scripts/just/check-pre-commit-doc-only.sh`) arms the tier whenever
the staged changeset touches the registry, reasoning that refusing an
unowned entry at authoring time is "the one arming that cannot block an
unrelated commit". Armed over EVERY entry that reasoning does not hold:
from 2026-08-16 to 2026-09-04 the tier judged all 58 pre-existing
unowned entries too, so a commit adding eight properly-owned entries
was refused on all 66 (`livespec-dev-tooling-3ztbdq`). The scope lever
is what makes the implementation match the stated intent.

Two properties keep the narrowing honest:

- IT NARROWS THE VERDICT, NEVER THE REPORT. An out-of-scope TODO is
  still emitted, at warning level and carrying an explicit
  `out_of_staged_scope` marker, so a pre-existing offender never
  becomes indistinguishable from a clean registry.
- AN UNCOMPUTABLE SCOPE FAILS CLOSED. When `git` cannot produce a
  comparable `HEAD` copy — not a repository, no such blob, a
  non-array or unparseable baseline — the tier reverts to the WHOLE
  registry and says so (`baseline_unreadable`). "I could not tell what
  changed" must never be spelled the same way as "nothing changed".

Release CI sets only the fail lever, so the ratified release-gate
verdict is untouched: this is an opt-in narrowing for the authoring
context, not a change to what a release rejects.

LIVENESS IS BEST-EFFORT AND ABSENT BY DEFAULT. No tracker is
configured for this repo family, and a release runs on hosted CI
that cannot reach a loopback ledger, so `_probe_work_item_liveness`
reports `None` (UNVERIFIED) rather than inventing a verdict. An
UNVERIFIED entry PASSES, but emits a `liveness_unverified`
diagnostic — an unreachable tracker is not a passing liveness
check, and the two must never be indistinguishable. Liveness is
deliberately confined to the release tier: a per-commit verdict
depending on mutable external state could flip master red with no
commit, which `.ai/ci-gate-discipline.md` treats as a real broken
state rather than a notification.

The check loads the JSON file (strict JSON, not JSONC) and
walks the array. If the file is missing or contains no TODO
entries, the check exits 0.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_COVERAGE_PATH = Path("tests") / "heading-coverage.json"
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"
_SCOPE_ENV_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_TODOS_TO_HEAD_DIFF"
_HEAD_REVISION = f"HEAD:{_COVERAGE_PATH.as_posix()}"


def _is_owned(*, entry: dict[str, object]) -> bool:
    """Return whether `entry` names a work-item that owns replacing its TODO.

    Absent, non-string, empty, and whitespace-only values are all UNOWNED —
    the ratified rule admits only a non-empty id.
    """
    work_item = entry.get("work_item")
    return isinstance(work_item, str) and bool(work_item.strip())


def _probe_work_item_liveness(*, work_item: str) -> bool | None:
    """Best-effort liveness probe for `work_item`; `None` means UNVERIFIED.

    ABSENT BY DEFAULT, and that is the shipped production behavior rather
    than a placeholder: this repo family configures no tracker at all, and
    the release gate runs on hosted CI that cannot reach a loopback ledger.
    Returning `None` keeps the check honest — it reports that liveness was
    not established instead of asserting a work-item is live.

    A consumer that configures a reachable tracker replaces this seam; the
    ratified rule only asks for liveness "where the configured tracker
    makes liveness mechanically checkable".
    """
    del work_item  # No tracker is configured; nothing to query.
    return None


def _entry_fingerprint(*, entry: object) -> str:
    """Canonical, key-order-independent rendering of one registry element.

    Two elements compare equal iff their VALUES agree, so reformatting the
    registry file or reordering an entry's keys is not read as "every entry
    changed" — only a changed value puts an entry back in scope.
    """
    return json.dumps(entry, sort_keys=True)


def _baseline_fingerprints(*, cwd: Path) -> frozenset[str] | None:
    """Fingerprints of the registry as of `HEAD`; `None` when it is NOT COMPARABLE.

    `None` never means "the registry was empty at HEAD" — it means no
    comparison is possible, which the caller turns into a whole-registry
    fallback. The arms it fuses all say exactly that: `cwd` is not a
    repository, `HEAD` carries no such blob (`git show` exits non-zero having
    printed nothing, so the empty stdout does not parse), the blob is not
    JSON, or it is JSON that is not an array. They are fused because they take
    the same response — judge everything — and separating them would only
    multiply diagnostics for one operator action.

    Every `GIT_*` variable is stripped from the child's environment. The
    caller this lever exists for IS a git commit hook, and git exports
    `GIT_DIR` / `GIT_INDEX_FILE` / `GIT_WORK_TREE` to its hooks; those
    OVERRIDE `cwd`, so an inherited environment would silently baseline
    against a different repository (the trap `_branch_diff` documents).
    """
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        # S603/S607: argv is a fixed list of literal git args; no shell input.
        completed = subprocess.run(
            ["git", "show", _HEAD_REVISION],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            env=git_env,
        )
        parsed = json.loads(completed.stdout)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, list):
        return None
    return frozenset(_entry_fingerprint(entry=element) for element in cast("list[object]", parsed))


def _in_scope_offenders(
    *, offenders: list[dict[str, object]], cwd: Path
) -> list[dict[str, object]]:
    """The offenders the staged commit is AUTHORING — added or modified since `HEAD`.

    An out-of-scope entry is warned about rather than dropped in silence: the
    armed tier stops JUDGING it, and must not stop REPORTING it, or the
    narrowing would make a pre-existing offender read like a clean registry.

    An uncomputable baseline returns `offenders` unchanged, so the tier falls
    back to judging the whole registry — the same verdict as before this lever
    existed, announced rather than assumed.
    """
    emit = structlog.get_logger("no_todo_registry")
    baseline = _baseline_fingerprints(cwd=cwd)
    if baseline is None:
        emit.warning(
            "staged-diff scope requested but HEAD's registry copy is not comparable — "
            "the armed tier falls back to judging the WHOLE registry",
            revision=_HEAD_REVISION,
            baseline_unreadable=True,
            failing=False,
        )
        return offenders
    in_scope: list[dict[str, object]] = []
    for entry in offenders:
        if _entry_fingerprint(entry=entry) in baseline:
            emit.warning(
                'heading-coverage.json entry has `test: "TODO"`; unchanged since HEAD, '
                "so the armed tier reports it without judging it",
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                out_of_staged_scope=True,
                failing=False,
            )
            continue
        in_scope.append(entry)
    return in_scope


def _warn_every_todo(*, offenders: list[dict[str, object]]) -> None:
    """PER-COMMIT tier: warn on every TODO entry regardless of ownership.

    Deliberately identical to the pre-ownership behavior, and that identity
    is load-bearing: it is what makes the release-tier narrowing a strict
    loosening that reddens no repository.
    """
    emit = structlog.get_logger("no_todo_registry")
    for entry in offenders:
        emit.warning(
            'heading-coverage.json entry has `test: "TODO"`',
            heading=entry.get("heading"),
            spec_root=entry.get("spec_root"),
            fail_env_var=_FAIL_ENV_VAR,
            failing=False,
        )


def _release_tier_failures(*, offenders: list[dict[str, object]]) -> int:
    """RELEASE tier: count entries that must block the release.

    Rejects an UNOWNED entry, and an owned one whose work-item is checkably
    closed or nonexistent. An owned entry whose liveness cannot be
    established PASSES, but emits a `liveness_unverified` diagnostic so it
    is never indistinguishable from a verified one.
    """
    emit = structlog.get_logger("no_todo_registry")
    failing = 0
    for entry in offenders:
        if not _is_owned(entry=entry):
            failing += 1
            emit.error(
                'heading-coverage.json entry has `test: "TODO"` with no owning `work_item`',
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                fail_env_var=_FAIL_ENV_VAR,
                failing=True,
            )
            continue
        work_item = cast("str", entry.get("work_item")).strip()
        live = _probe_work_item_liveness(work_item=work_item)
        if live is None:
            emit.warning(
                "owned TODO entry accepted; work-item liveness UNVERIFIED "
                "(no reachable tracker configured)",
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                work_item=work_item,
                liveness_unverified=True,
                failing=False,
            )
        elif not live:
            failing += 1
            emit.error(
                'heading-coverage.json entry has `test: "TODO"` owned by a '
                "closed or nonexistent work-item",
                heading=entry.get("heading"),
                spec_root=entry.get("spec_root"),
                work_item=work_item,
                fail_env_var=_FAIL_ENV_VAR,
                failing=True,
            )
    return failing


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    cwd = Path.cwd()
    coverage_path = cwd / _COVERAGE_PATH
    if not coverage_path.is_file():
        return 0
    text = coverage_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    offenders: list[dict[str, object]] = []
    if isinstance(parsed, list):
        # The `cast` is the single typed parse boundary: `json.loads` yields
        # `Any`, the `isinstance` guard narrows to `list`, and the cast gives
        # the elements a typed `object` shape so the per-element
        # `isinstance(entry, dict)` filter stays a load-bearing runtime guard.
        # The compound condition (single `if`, inline cast evaluated only
        # after the isinstance short-circuit) preserves the original branch
        # shape — no new branch, so coverage stays 100%.
        entries = cast("list[object]", parsed)
        for entry in entries:
            if isinstance(entry, dict) and cast("dict[str, object]", entry).get("test") == "TODO":
                offenders.append(cast("dict[str, object]", entry))
    if not offenders:
        return 0
    if not bool(os.environ.get(_FAIL_ENV_VAR)):
        _warn_every_todo(offenders=offenders)
        return 0
    if bool(os.environ.get(_SCOPE_ENV_VAR)):
        offenders = _in_scope_offenders(offenders=offenders, cwd=cwd)
    return 1 if _release_tier_failures(offenders=offenders) else 0


if __name__ == "__main__":
    raise SystemExit(main())
