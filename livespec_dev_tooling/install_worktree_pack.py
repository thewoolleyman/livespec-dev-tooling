"""install_worktree_pack — install the canonical livespec worktree-discipline pack.

Writes the canonical worktree-discipline pack into a governed repo's
`dev-tooling/` directory. The pack is three files from a single package
source: the two executable shell scripts `worktree-lib.sh` (the portable,
ecosystem-neutral worktree-lifecycle core) and `branch-protection.sh` (the
server-side branch-protection mirror), plus the non-executable justfile
fragment `worktree.just` (the four `just worktree-*` lifecycle recipe
stanzas, the consumer root justfile `import`s rather than copies). The two
`.sh` scripts are made executable (the recipes invoke them directly via
`./dev-tooling/…`); `worktree.just` is a justfile fragment that is `import`ed,
never run directly, so it is NOT made executable. The target directory is the
repository's work-tree root resolved via `git rev-parse --show-toplevel`, so
the pack lands beside the consumer's other `dev-tooling/` scripts and is
committed through the normal worktree → PR flow. This differs from the
commit-refuse hook precedent's install target: the pack files are TRACKED
repo files under `dev-tooling/`, whereas the hooks live in the untracked
shared `.git/hooks/` directory.

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
zero escaping, and the package file IS the single canonical source. The
`worktree.just` recipe fragment ships the same way — a genuine package-data
file (ruff does not lint `.just`), not a `.py` string constant. This module
still EXPOSES the three bodies as the `CANONICAL_WORKTREE_LIB_BODY` /
`CANONICAL_BRANCH_PROTECTION_BODY` / `CANONICAL_WORKTREE_JUST_BODY` string
constants (read once at import), so the
`primary_checkout_commit_refuse_hook_installed` verifier imports the SAME
constants to assert byte-identity against the installed files — there is no
second copy to drift.

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

import stat
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "CANONICAL_BRANCH_PROTECTION_BODY",
    "CANONICAL_WORKTREE_JUST_BODY",
    "CANONICAL_WORKTREE_LIB_BODY",
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


# The three canonical bodies, read once at import from package-data. Exposed
# as module constants so the verifier imports the SAME bytes it asserts the
# installed files against (no drift seam).
CANONICAL_WORKTREE_LIB_BODY = _read_canonical_body(name="worktree-lib.sh")
CANONICAL_BRANCH_PROTECTION_BODY = _read_canonical_body(name="branch-protection.sh")
CANONICAL_WORKTREE_JUST_BODY = _read_canonical_body(name="worktree.just")


# The pack's installed layout: `(basename, canonical body, executable)`
# tuples written under the consumer repo's `dev-tooling/` directory. The two
# `.sh` scripts are made executable (the `worktree-*` recipes invoke them
# directly via `./dev-tooling/…`); `worktree.just` is a justfile fragment the
# consumer root justfile `import`s — never run directly — so it is installed
# NON-executable.
_PACK_FILES: tuple[tuple[str, str, bool], ...] = (
    ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY, True),
    ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY, True),
    ("worktree.just", CANONICAL_WORKTREE_JUST_BODY, False),
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

    Uses `git rev-parse --show-toplevel`. The pack is a set of TRACKED
    repo files under `dev-tooling/`, so it installs into the work-tree
    root of wherever the installer runs (then committed through the
    normal worktree → PR flow). Uses `check=True` so a failed invocation
    raises (a bug — the installer is only ever run inside a repo) rather
    than silently returning a sentinel.
    """
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(completed.stdout.strip())


def install_pack(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Install the canonical worktree pack into `<work-tree-root>/dev-tooling/`.

    Writes each `_PACK_FILES` body to `<root>/dev-tooling/<name>`, setting
    the executable bit only on the entries flagged executable (the two `.sh`
    scripts; the `worktree.just` recipe fragment is `import`ed, never run, so
    it stays non-executable). Idempotent: re-running overwrites with the
    identical canonical bodies. Returns 0 on success.
    """
    pack_dir = _work_tree_root(cwd=cwd) / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for name, body, executable in _PACK_FILES:
        path = pack_dir / name
        _ = path.write_text(body, encoding="utf-8")
        if executable:
            current_mode = path.stat().st_mode
            path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        log.info(
            "installed canonical worktree-pack file",
            file=name,
            executable=executable,
            path=str(path),
        )
    return 0


def main() -> int:
    log = _configure_logger()
    return install_pack(cwd=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
