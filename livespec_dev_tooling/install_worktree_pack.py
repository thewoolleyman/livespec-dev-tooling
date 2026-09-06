"""install_worktree_pack — install the canonical livespec worktree-discipline pack.

Writes the canonical worktree-discipline pack into a governed repo's
`dev-tooling/` directory. The pack is seven files from a single package
source/generator pair: the four executable shell scripts `worktree-lib.sh`
(the portable, ecosystem-neutral worktree-lifecycle core),
`branch-protection.sh` (the server-side branch-protection mirror),
`gate-run.sh` (the detached gate runner), and `check-no-workflow-edits.sh`
(the fleet's one workflow-edit guard — an authorship control at the agent
boundary with a ledger-verified human-authorization override, no
environment escape; livespec-dev-tooling-fy02), plus the two non-executable
justfile fragments `worktree.just` (the four `just worktree-*` lifecycle
recipe stanzas) and `branch-protection.just` (the `protect-default-branch` /
`check-branch-protection` recipe stanzas), each `import`ed by the consumer
root justfile rather than copied, plus a generated `.gitignore` that ignores
the installed pack entries. The four `.sh` scripts are made executable
(the recipes invoke them directly via `./dev-tooling/…`); the two `.just`
fragments are `import`ed, never run directly, so they are NOT made
executable. The target directory is the repository's work-tree root resolved
via `git rev-parse --show-toplevel`, so the pack lands beside the consumer's
other `dev-tooling/` files.

The pack files are UNTRACKED-AND-INSTALLED, NOT tracked-committed: a consumer
`git rm`s them from version control, gitignores them, and (re)materializes
them via `just install-worktree-pack` from `bootstrap`/CI. This mirrors the
commit-refuse hook precedent, which installs its single canonical body into
the untracked shared `.git/hooks/` directory — the only difference is the
install target (`dev-tooling/` here, `.git/hooks/` for the hooks). Because
nothing tracks the installed copy, the `primary_checkout_commit_refuse_hook_installed`
verifier byte-checks it against the package source on every `just check`.

DELIVERY CARRIER — package-data, not an inline string constant. The
commit-refuse hook precedent (`install_commit_refuse_hooks`) embeds its
canonical body as a module-level Python string. That carrier does not
transfer to the worktree pack: the pack's shell legitimately carries lines
longer than the 100-column lint limit (e.g. `branch-protection.sh`'s `gh
api` invocations and trip messages), so embedding ~700 lines of shell into
a `.py` would trip ruff `E501` on every long physical line and force a
per-file lint exemption — exactly the "fix the gate, not the bypass"
anti-pattern the project forbids. Instead the canonical bodies ship as
genuine PACKAGE-DATA files under `livespec_dev_tooling/worktree_pack/`
(resolved by `__file__`-relative path, mirroring the existing `_VENDOR_DIR`
pattern). ruff never lints those `.sh` files, the bytes stay faithful with
zero escaping, and the package file IS the single canonical source. The two
`.just` recipe fragments ship the same way — genuine package-data files (ruff
does not lint `.just`), not `.py` string constants. This module still EXPOSES
the six bodies as the `CANONICAL_WORKTREE_LIB_BODY` /
`CANONICAL_BRANCH_PROTECTION_BODY` / `CANONICAL_GATE_RUN_BODY` /
`CANONICAL_NO_WORKFLOW_EDITS_BODY` / `CANONICAL_WORKTREE_JUST_BODY` /
`CANONICAL_BRANCH_PROTECTION_JUST_BODY` string constants (read once at
import), and pairs each with its basename in `WORKTREE_PACK_FILES` — so the
`primary_checkout_commit_refuse_hook_installed` verifier walks the SAME
constant to assert byte-identity against the installed files, and there is no
second copy to drift.

ONE ENUMERATION OF THE FILE SET, not just of the bodies. Sharing the bodies
was never enough: the SET each consumer walked was hand-written per consumer,
and measured 2026-09-06 the three copies disagreed — the verifier asserted
six files, the `worktree-pack` bootstrap obligation row asserted four, and
`worktree-lib.sh` carried a third copy as a shell string. `just bootstrap`
therefore passed a pack `just check` rejected. `WORKTREE_PACK_FILES` below is
now the single enumeration of `(name, body, executable)`; the installer, the
verifier's pack arm, and `fleet/_rows_local.py::assert_worktree_pack` all walk
IT, and the shell copy is held to it by a lockstep test
(livespec-dev-tooling-l5gypl).

Retires the copy-based delivery: the bodies were previously shipped ONLY as
copier-template COPIES under livespec core's
`templates/impl-plugin/dev-tooling/`, which violates the fleet "reuse, no
copies" delivery rule and is drift-prone. Shipping them as package-data
plus this installer makes the package the single canonical source. The
per-ecosystem `worktree-hydrate.sh` stub is deliberately NOT part of this
pack — it is legitimately per-ecosystem and stays a copier template the
consuming repo replaces with its ecosystem-correct hydration.

CLI:
    python -m livespec_dev_tooling.install_worktree_pack
        Install (or idempotently re-install) the canonical worktree pack
        into the current repo's `dev-tooling/` directory. Exits 0 on
        success.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.
import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "CANONICAL_BRANCH_PROTECTION_BODY",
    "CANONICAL_BRANCH_PROTECTION_JUST_BODY",
    "CANONICAL_GATE_RUN_BODY",
    "CANONICAL_NO_WORKFLOW_EDITS_BODY",
    "CANONICAL_WORKTREE_JUST_BODY",
    "CANONICAL_WORKTREE_LIB_BODY",
    "CANONICAL_WORKTREE_PACK_GITIGNORE_BODY",
    "WORKTREE_PACK_FILES",
    "PackFile",
    "install_pack",
    "main",
]


# The packaged canonical bodies live beside this module under
# `worktree_pack/`, resolved `__file__`-relatively exactly as `_VENDOR_DIR`
# above is — the established house pattern for package-shipped resources
# (livespec-dev-tooling installs unpacked, so a filesystem path is sound).
_PACK_DATA_DIR = Path(__file__).resolve().parent / "worktree_pack"


def _read_canonical_body(*, name: str) -> str:
    """Read a packaged canonical pack script body (utf-8) by basename."""
    return (_PACK_DATA_DIR / name).read_text(encoding="utf-8")


# The six canonical bodies, read once at import from package-data. Exposed
# as module constants so the verifier imports the SAME bytes it asserts the
# installed files against (no drift seam).
CANONICAL_WORKTREE_LIB_BODY = _read_canonical_body(name="worktree-lib.sh")
CANONICAL_BRANCH_PROTECTION_BODY = _read_canonical_body(name="branch-protection.sh")
CANONICAL_WORKTREE_JUST_BODY = _read_canonical_body(name="worktree.just")
CANONICAL_BRANCH_PROTECTION_JUST_BODY = _read_canonical_body(name="branch-protection.just")
CANONICAL_GATE_RUN_BODY = _read_canonical_body(name="gate-run.sh")
CANONICAL_NO_WORKFLOW_EDITS_BODY = _read_canonical_body(name="check-no-workflow-edits.sh")


@dataclass(frozen=True, kw_only=True)
class PackFile:
    """One installed pack file: its basename, canonical body and executable bit.

    The member type of `WORKTREE_PACK_FILES`, which is the SINGLE enumeration
    of the pack's shape. Every consumer walks that tuple — `install_pack`
    below, the `primary_checkout_commit_refuse_hook_installed` pack arm, and
    the `worktree-pack` bootstrap obligation row — so none of them can hold a
    set the others do not.
    """

    name: str
    body: str
    executable: bool


# The pack's installed payload, before adding its generated ignore file. This
# is the ONLY place a pack file's name, body and executable bit are written
# down; `WORKTREE_PACK_FILES` below appends the ignore file whose body is
# DERIVED from this tuple, and every consumer reads that. The `.sh` scripts are
# made executable (the recipes invoke them directly via `./dev-tooling/…`); the
# `.just` fragments (`worktree.just`, `branch-protection.just`) are `import`ed
# by the consumer root justfile — never run directly — so they are installed
# NON-executable, as is the generated ignore file.
_PACK_PAYLOAD_FILES: tuple[PackFile, ...] = (
    PackFile(name="worktree-lib.sh", body=CANONICAL_WORKTREE_LIB_BODY, executable=True),
    PackFile(name="branch-protection.sh", body=CANONICAL_BRANCH_PROTECTION_BODY, executable=True),
    PackFile(name="gate-run.sh", body=CANONICAL_GATE_RUN_BODY, executable=True),
    PackFile(
        name="check-no-workflow-edits.sh",
        body=CANONICAL_NO_WORKFLOW_EDITS_BODY,
        executable=True,
    ),
    PackFile(name="worktree.just", body=CANONICAL_WORKTREE_JUST_BODY, executable=False),
    PackFile(
        name="branch-protection.just",
        body=CANONICAL_BRANCH_PROTECTION_JUST_BODY,
        executable=False,
    ),
)

CANONICAL_WORKTREE_PACK_GITIGNORE_BODY = "".join(
    [
        "# Generated by livespec_dev_tooling.install_worktree_pack.\n",
        "# Ignore the untracked package-installed worktree pack.\n",
        *[f"/{pack_file.name}\n" for pack_file in _PACK_PAYLOAD_FILES],
        "/.gitignore\n",
    ]
)

# THE pack file set — the one enumeration every consumer derives from. The
# generated ignore file comes last, and because its body is derived from
# `_PACK_PAYLOAD_FILES`, adding a future payload to the installer automatically
# adds the matching ignore rule.
WORKTREE_PACK_FILES: tuple[PackFile, ...] = (
    *_PACK_PAYLOAD_FILES,
    PackFile(
        name=".gitignore",
        body=CANONICAL_WORKTREE_PACK_GITIGNORE_BODY,
        executable=False,
    ),
)


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("install_worktree_pack")


def _work_tree_root(*, cwd: Path) -> Path:
    """Return the absolute path to the git work-tree root for `cwd`.

    Uses `git rev-parse --show-toplevel`. The pack is a set of
    UNTRACKED-AND-INSTALLED files under `dev-tooling/` (gitignored, never
    tracked-committed), so it installs into the work-tree root of wherever
    the installer runs. Uses `check=True` so a failed invocation raises (a
    bug — the installer is only ever run inside a repo) rather than silently
    returning a sentinel.
    """
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(completed.stdout.strip())


_LIVESPEC_JSONC_NAME = ".livespec.jsonc"
_WORKTREE_DISCIPLINE_KEY = "worktree_discipline"

# The declaration an operator commits, offered verbatim so the key arrives WITH
# its rationale. The verifier treats an absent key as `required`; without this
# block that default is folklore a new adopter can only discover by tripping
# the check. Indentation matches the two-space house style of the governed
# `.livespec.jsonc` files.
_WORKTREE_DISCIPLINE_DEFAULT_BLOCK = """\
  // Worktree-discipline pack policy. "required" — the DEFAULT, and what an
  // absent key means — makes `just check` fail when the canonical pack is not
  // installed and imported by the root justfile. "optional" is the sanctioned,
  // reviewable opt-out. Declared explicitly so the obligation is readable here
  // rather than inferred from a verifier failure.
  "worktree_discipline": { "pack": "required" },
"""

_WORKTREE_DISCIPLINE_UNDECLARED_EVENT = (
    "worktree_discipline undeclared — an absent key already MEANS `pack: required`; "
    "commit the block in `declare` to state it"
)


def _report_undeclared_worktree_discipline(
    *, root: Path, log: structlog.stdlib.BoundLogger
) -> None:
    """Report an undeclared `worktree_discipline`; NEVER touch `.livespec.jsonc`.

    DETECT-AND-GUIDE, NOT WRITE — the shape the beads-runtime rows already use
    for a seam they cannot machine-fix. This used to SPLICE the block above into
    `<root>/.livespec.jsonc` after a `{`-only anchor line. That file is TRACKED
    and nothing commits the result, so the sanctioned first-touch command left
    the checkout dirty BY CONSTRUCTION in every repo that had not already
    committed the key, re-made the same modification on every subsequent run,
    and converged on nothing: measured 2026-08-04 across a six-repo sweep as
    exactly one modified `.livespec.jsonc` in six of six fresh worktrees, from
    clean primaries. The blast radius was never just `bootstrap` — `just
    install-worktree-pack` is the FIRST lefthook command of BOTH `pre-commit`
    and `pre-push` in every wired repo, so the write reached every commit and
    every push. And a dirty SOURCE checkout is precisely the precondition the
    dispatcher's pre-clone preflight exists to clear, where it does not present
    as dirt at all but as a misleading GitHub `workflows`-permission rejection.

    Dropping the write costs NOTHING BEHAVIOURAL and is conformance rather than
    a change of policy: `SPECIFICATION/non-functional-requirements.md` already
    requires this installer to "write only files the repository ignores"; an
    absent key already MEANS `required` to `_primary_checkout_worktree_pack`;
    and the central `worktree-pack-wired` fleet row already reports the missing
    declaration at error severity with the exact line to commit. What the splice
    was actually reaching for — making the obligation READABLE in config instead
    of discoverable by tripping a verifier — is served by handing the operator
    the block, which is what this logs.

    Three deliberate silences:

    - **No `.livespec.jsonc`** → say nothing. Its absence means the directory is
      not governed, so there is no declaration to be missing.
    - **Unparseable config** → say nothing. The key set of a document that does
      not parse is unknown, and the config-integrity check already owns that
      diagnosis; a second voice there is noise, not signal.
    - **Key already present** → say nothing, whatever its value. A declared
      `"optional"` is a reviewed decision, and nagging about a stated policy
      would make the sanctioned escape hatch feel like a defect.
    """
    config_path = root / _LIVESPEC_JSONC_NAME
    if not config_path.is_file():
        return
    try:
        parsed = jsoncomment.loads(config_path.read_text(encoding="utf-8"))
    except (ValueError, json.JSONDecodeError):
        return
    if not isinstance(parsed, dict) or _WORKTREE_DISCIPLINE_KEY in parsed:
        return
    log.info(
        _WORKTREE_DISCIPLINE_UNDECLARED_EVENT,
        path=str(config_path),
        declare=_WORKTREE_DISCIPLINE_DEFAULT_BLOCK,
    )


# The three dispositions `_install_pack_file` reports through the log's
# `changed` field. The installer runs on EVERY commit and EVERY push in a wired
# repo, so the overwhelmingly common line is `none` — an operator reading the
# gate's output needs to tell that steady state from a real heal at a glance,
# and needs `mode` distinguishable from `body` because the two say different
# things about how the worktree drifted.
_CHANGED_BODY = "body"
_CHANGED_MODE = "mode"
_CHANGED_NONE = "none"


def _installed_matches(*, path: Path, body: str) -> bool:
    """Whether `path` already holds exactly `body`.

    The read that replaces an unconditional write. `is_file()` first so an
    absent member — the fresh-worktree case — answers False without raising,
    and so a directory sitting where a pack file belongs is treated as drift to
    be overwritten rather than crashing the gate.
    """
    return path.is_file() and path.read_bytes() == body.encode("utf-8")


def _apply_mode(*, path: Path, pack_file: PackFile) -> bool:
    """Ensure `path`'s executable bits match `pack_file`; True when chmod ran.

    Only ever ADDS the bits, and only for members flagged executable. Bytes say
    nothing about mode, so skipping the identical write would otherwise leave a
    canonical-but-unexecutable `gate-run.sh` unrepaired — and it is invoked
    directly as `./dev-tooling/gate-run.sh`. A `chmod` leaves mtime alone, so
    the repair still costs no rewrite.
    """
    if not pack_file.executable:
        return False
    current_mode = path.stat().st_mode
    wanted_mode = current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if wanted_mode == current_mode:
        return False
    path.chmod(wanted_mode)
    return True


def _install_pack_file(*, path: Path, pack_file: PackFile) -> str:
    """Bring one pack member to its canonical body and mode; say what changed."""
    if not _installed_matches(path=path, body=pack_file.body):
        _ = path.write_text(pack_file.body, encoding="utf-8")
        _ = _apply_mode(path=path, pack_file=pack_file)
        return _CHANGED_BODY
    if _apply_mode(path=path, pack_file=pack_file):
        return _CHANGED_MODE
    return _CHANGED_NONE


def install_pack(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Install the canonical worktree pack into `<work-tree-root>/dev-tooling/`.

    Brings each `WORKTREE_PACK_FILES` member to its canonical body at
    `<root>/dev-tooling/<name>`, setting the executable bit only on the entries
    flagged executable (the four `.sh` scripts; the two `.just` recipe
    fragments are `import`ed, never run, so they stay non-executable, as does
    the generated ignore file). Returns 0 on success.

    IDEMPOTENT BY READ, NOT BY REWRITE. This used to write every body
    unconditionally, which was harmless when the only callers were `bootstrap`
    and CI. It is no longer: `just install-worktree-pack` is now the first
    lefthook command of `pre-commit` AND `pre-push` in every wired repo, so an
    unconditional write would churn every pack mtime on every commit and every
    push for a pack that is almost always already canonical. A member whose
    installed bytes already match is left alone, and one whose bytes match but
    whose mode does not is repaired with a `chmod` alone — making the
    steady-state per-hook cost a read.

    READ-ONLY WITH RESPECT TO TRACKED FILES. Everything written lands under the
    gitignored `dev-tooling/`; the one governed file this touches,
    `.livespec.jsonc`, is only READ, and an undeclared `worktree_discipline` is
    REPORTED rather than spliced in (see `_report_undeclared_worktree_discipline`
    for what that write cost and why nothing behavioural rested on it).
    """
    root = _work_tree_root(cwd=cwd)
    pack_dir = root / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for pack_file in WORKTREE_PACK_FILES:
        path = pack_dir / pack_file.name
        log.info(
            "installed canonical worktree-pack file",
            file=pack_file.name,
            executable=pack_file.executable,
            changed=_install_pack_file(path=path, pack_file=pack_file),
            path=str(path),
        )
    _report_undeclared_worktree_discipline(root=root, log=log)
    return 0


def main() -> int:
    log = _configure_logger()
    return install_pack(cwd=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
