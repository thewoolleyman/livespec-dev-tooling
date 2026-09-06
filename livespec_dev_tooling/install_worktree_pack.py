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

# The provisioned default block, written verbatim so the key arrives WITH its
# rationale. The verifier treats an absent key as `required`; without this
# block that default is folklore a new adopter can only discover by tripping
# the check. Indentation matches the two-space house style of the governed
# `.livespec.jsonc` files.
_WORKTREE_DISCIPLINE_DEFAULT_BLOCK = """\
  // Worktree-discipline pack policy. "required" — the DEFAULT, and what an
  // absent key means — makes `just check` fail when the canonical pack is not
  // installed and imported by the root justfile. "optional" is the sanctioned,
  // reviewable opt-out. Written explicitly at install time so the obligation is
  // readable here rather than inferred from a verifier failure.
  "worktree_discipline": { "pack": "required" },
"""


def _ensure_worktree_discipline_default(*, root: Path, log: structlog.stdlib.BoundLogger) -> None:
    """Write `worktree_discipline` with its default into `<root>/.livespec.jsonc`.

    Three deliberate no-ops:

    - **No `.livespec.jsonc`** → do nothing. Its absence means the directory is
      not governed, and minting a governance file as a side effect of
      installing recipe fragments would be a surprising mutation.
    - **Key already present** → do nothing, whatever its value. A declared
      `"optional"` is a reviewed decision; silently rewriting it to `required`
      would make the sanctioned escape hatch unusable and turn `just bootstrap`
      into a config mutation nobody asked for.
    - **No `{`-only anchor line** → do nothing. The file is JSONC WITH
      COMMENTS, so this splices text rather than re-serializing: a `json.dumps`
      round-trip would silently delete every comment in a consumer's config.
      When the opening brace is not on its own line there is no safe splice
      point, so the installer declines rather than guessing.
    """
    config_path = root / _LIVESPEC_JSONC_NAME
    if not config_path.is_file():
        return
    text = config_path.read_text(encoding="utf-8")
    try:
        parsed = jsoncomment.loads(text)
    except (ValueError, json.JSONDecodeError):
        return
    if not isinstance(parsed, dict) or _WORKTREE_DISCIPLINE_KEY in parsed:
        return
    lines = text.splitlines(keepends=True)
    anchor = next((i for i, line in enumerate(lines) if line.strip() == "{"), None)
    if anchor is None:
        log.info(
            "skipped worktree_discipline default: no splice anchor",
            path=str(config_path),
        )
        return
    lines.insert(anchor + 1, _WORKTREE_DISCIPLINE_DEFAULT_BLOCK)
    _ = config_path.write_text("".join(lines), encoding="utf-8")
    log.info(
        "wrote worktree_discipline default",
        path=str(config_path),
        pack="required",
    )


def install_pack(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Install the canonical worktree pack into `<work-tree-root>/dev-tooling/`.

    Writes each `WORKTREE_PACK_FILES` body to `<root>/dev-tooling/<name>`,
    setting the executable bit only on the entries flagged executable (the four
    `.sh` scripts; the two `.just` recipe fragments are `import`ed, never run,
    so they stay non-executable, as does the generated ignore file).
    Idempotent: re-running overwrites with the identical canonical bodies.
    Returns 0 on success.
    """
    root = _work_tree_root(cwd=cwd)
    pack_dir = root / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for pack_file in WORKTREE_PACK_FILES:
        path = pack_dir / pack_file.name
        _ = path.write_text(pack_file.body, encoding="utf-8")
        if pack_file.executable:
            current_mode = path.stat().st_mode
            path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        log.info(
            "installed canonical worktree-pack file",
            file=pack_file.name,
            executable=pack_file.executable,
            path=str(path),
        )
    _ensure_worktree_discipline_default(root=root, log=log)
    return 0


def main() -> int:
    log = _configure_logger()
    return install_pack(cwd=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
