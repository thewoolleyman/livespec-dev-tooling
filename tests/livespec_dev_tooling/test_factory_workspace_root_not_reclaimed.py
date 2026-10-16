"""Nothing committed here may remove, empty or remount `/srv/factory-workspaces`.

THE QUESTION THIS FILE ANSWERS (work-item livespec-dev-tooling-due2h6,
Definition of Done assertion 2). The factory workspace root is node-local state
that no cluster object recreates: a boot-time converge or a storage reclaimer
that deletes it takes a live factory run's workspace with it, and it does so
SILENTLY — the directory is simply gone, the next pod's hostPath is empty, and
nothing in the pod explains why. `ansible/roles/factory_workspace_root/` creates
it; this file is the other half, and it says what must NOT happen to it.

HOW THE CLAIM IS ESTABLISHED, in three complementary ways, because no one of
them is sufficient on its own:

1. **Non-collision, by scan.** Every committed shell script, Ansible task file,
   template and systemd unit under `ansible/` and `ci-runner/` is read, and
   every absolute path literal appearing in the WINDOW around a destructive
   statement (`rm -r`, `rmdir`, `shred`, `-delete`, `mkfs`, `wipefs`, `sgdisk`,
   `umount`, `truncate`, Ansible's `state: absent`) is checked against the
   workspace root for a PREFIX RELATIONSHIP in either direction — an ancestor
   (`/srv`, `/`) deletes it wholesale, a descendant empties it. A window rather
   than a line, because an Ansible task says `state: absent` on one line and
   names its `path:` on another, and a line reader would see neither as
   destructive.
2. **Non-naming, by exactness.** The path literal appears in the whole
   `ansible/` + `ci-runner/` tree ONLY where it is declared, documented, or
   DENIED. That is what closes the gap the scan cannot: a path assembled at
   runtime from a variable is invisible to any reader of literals, so instead of
   trying to read it, this arm establishes that no other artifact names the path
   at all — not as an fstab line, not as a mount unit, not as a sweep root.
3. **Deny-listing, by code.** The two reclaimers that actually run on a Fabro
   factory host — `storage-reclaim.sh` and `container-reclaim.sh`, both applied
   to `hp-xubuntu` by `ansible/fabro-hosts.yml` — carry the workspace root in
   their own `DENY_ROOTS`, so neither can be pointed at it even by a host
   variable that nothing in this repository spells. `storage-reclaim.sh`'s own
   comment records why that matters: with a root of `/srv`, `/srv/anything` is
   legitimately under the root and every other guard passes.

THE SCANNER IS PROVEN BEFORE IT IS TRUSTED. A derived scan that matched nothing
would report success over an unread tree, so the reader is fed synthetic
destructive statements — the path itself, an ancestor, a descendant, and an
Ansible `state: absent` task — and must flag every one, while a sibling path
(`/srv/sandbox-storage`, which a real role does manage) must NOT be flagged. The
set of files scanned is also held to containing the artifacts the work-item
names by hand: the boot converge, the phase0 storage recipe, the boot-ordered
scratch sweep, and both reclaimers.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "factory_workspace_root" / "defaults/main.yml"
_ROLE_CAPACITY = _REPO_ROOT / "ansible" / "roles" / "factory_workspace_root" / "CAPACITY.md"
_STORAGE_RECLAIM = _REPO_ROOT / "ansible/roles/storage_reclaim/files/storage-reclaim.sh"
_CONTAINER_RECLAIM = _REPO_ROOT / "ansible/roles/container_reclaim/files/container-reclaim.sh"
_SCRATCH_SWEEP = _REPO_ROOT / "ci-runner/k3s/phase2/storage-sweep/sweep-runner-scratch.sh"
_BOOT_CONVERGE = _REPO_ROOT / "ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh"
_PHASE0_LAYOUT = _REPO_ROOT / "ci-runner/k3s/phase0-bare-metal/storage-layout.sh"

# The two trees that carry everything this repository installs on a node, and
# the file kinds that can destroy a directory. A `.md` cannot; a `.json` cannot.
_SCANNED_TREES = ("ansible", "ci-runner")
_SCANNED_SUFFIXES = frozenset({".sh", ".yml", ".yaml", ".service", ".timer", ".j2", ".conf"})

# Every artifact that MUST be inside the scan, named by hand because a scan that
# silently matched zero of them would pass. The work-item names the first two;
# the sweep is the only boot-ordered deleter in the tree; the reclaimers are the
# two that run on a factory host.
_MUST_BE_SCANNED = (
    _BOOT_CONVERGE,
    _PHASE0_LAYOUT,
    _SCRATCH_SWEEP,
    _STORAGE_RECLAIM,
    _CONTAINER_RECLAIM,
)

# A statement that can destroy a directory. `rm` is matched with a recursive or
# force flag; `state: absent` is Ansible's spelling; `umount` and `mkfs` are the
# remount and reformat halves of "removes, empties or remounts".
_DESTRUCTIVE = re.compile(
    r"\brm\s+-\w*[rRf]"
    r"|\brmdir\b"
    r"|\bshred\b"
    r"|-delete\b"
    r"|\bmkfs(?:\.\w+)?\b"
    r"|\bwipefs\b"
    r"|\bsgdisk\b"
    r"|\bumount\b"
    r"|\btruncate\b"
    r"|state:\s*absent"
)
# An absolute path LITERAL. The first component must start with a letter, so a
# stray `/` closing a quoted variable expansion (`"${dir}/"`) is not read as the
# root filesystem — a false positive that would make this reader useless rather
# than strict.
_ABSOLUTE_PATH = re.compile(r"(?P<path>/[A-Za-z][\w./*-]*)")
# Lines either side of a destructive statement that count as the same statement.
# Ansible's `path:` and `state: absent` are different lines of one task, and a
# shell `rm` is sometimes two lines from the variable assignment above it.
_WINDOW = 8

_WORKSPACE_ROOT_DECLARATION = re.compile(
    r"^factory_workspace_root_path: (?P<path>\S+)$", re.MULTILINE
)
# `readonly DENY_ROOTS=(/ /srv …)` — the one line each reclaimer states its
# untouchable roots on.
_DENY_ROOTS = re.compile(r"^readonly DENY_ROOTS=\((?P<roots>[^)]*)\)", re.MULTILINE)
# The boot-ordered sweep's own root, as the script defaults it.
_SWEEP_ROOT = re.compile(r'^STORAGE_ROOT="\$\{STORAGE_ROOT:-(?P<root>[^}]+)\}"', re.MULTILINE)


def _workspace_root() -> str:
    """The path the role declares — read from the role, never restated here."""
    assert _ROLE_DEFAULTS.is_file(), (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} must be committed: this file asserts what "
        f"may not happen to the workspace root, and a path nothing declares is a path this "
        f"test would be asserting about from memory"
    )
    declared = _WORKSPACE_ROOT_DECLARATION.search(_ROLE_DEFAULTS.read_text(encoding="utf-8"))
    assert declared is not None, (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} must declare `factory_workspace_root_path: "
        f"<path>` on one line — it is the single source both the role and this test read the "
        f"workspace root from"
    )
    return declared["path"]


def _collides(*, path: str) -> bool:
    """True when `path` and the workspace root are in a prefix relationship.

    Both directions are collisions and for different reasons: an ANCESTOR
    (`/srv`, `/`) removes the workspace root wholesale, and a DESCENDANT empties
    it. A trailing glob or slash is stripped first, because `rm -rf /srv/*`
    deletes the same directory `rm -rf /srv` does.
    """
    candidate = path.rstrip("*").rstrip("/")
    root = _workspace_root()
    if not candidate:
        return True
    return candidate == root or root.startswith(f"{candidate}/") or candidate.startswith(f"{root}/")


def _destructive_path_literals(*, text: str) -> frozenset[str]:
    """Every absolute path literal in the window around a destructive statement.

    Full-line comments are blanked rather than dropped, so the surviving line
    numbers still align the window with the code it belongs to. A comment
    describing a deletion is not a deletion, and the trees being read are heavily
    commented — `storage-reclaim.sh` explains its own deny list in prose that
    names `/srv` beside the word it guards.
    """
    lines = ["" if line.lstrip().startswith("#") else line for line in text.splitlines()]
    found: set[str] = set()
    for index, line in enumerate(lines):
        if _DESTRUCTIVE.search(line) is None:
            continue
        window = "\n".join(lines[max(0, index - _WINDOW) : index + _WINDOW + 1])
        found.update(match["path"] for match in _ABSOLUTE_PATH.finditer(window))
    return frozenset(found)


def _scanned_files() -> tuple[Path, ...]:
    """Every committed artifact under the two trees that could destroy a directory."""
    return tuple(
        sorted(
            path
            for tree in _SCANNED_TREES
            for path in (_REPO_ROOT / tree).rglob("*")
            if path.is_file() and path.suffix in _SCANNED_SUFFIXES
        )
    )


def _deny_roots(*, script: Path) -> tuple[str, ...]:
    """The `DENY_ROOTS` a reclaimer refuses to be pointed at."""
    assert script.is_file(), f"{script.relative_to(_REPO_ROOT)} must be committed"
    declared = _DENY_ROOTS.search(script.read_text(encoding="utf-8"))
    assert declared is not None, (
        f"{script.relative_to(_REPO_ROOT)} must declare its untouchable roots as one "
        f"`readonly DENY_ROOTS=(…)` line — it is the chokepoint every deletion in that script "
        f"passes through, and a list spread over several lines is one no reader can resolve"
    )
    return tuple(declared["roots"].split())


def test_the_reader_flags_a_destructive_statement_and_spares_a_sibling_path() -> None:
    """The control on the scan below: prove the reader bites before trusting its silence.

    Four shapes must be flagged — the path itself, an ancestor that takes it
    wholesale, a descendant that empties it, and an Ansible task whose
    `state: absent` and `path:` are different lines — and one must not:
    `/srv/sandbox-storage`, a real sibling that `ansible/roles/sandbox_storage/`
    legitimately migrates and reclaims. Without this arm, a reader that matched
    nothing at all would report the whole tree clean.
    """
    root = _workspace_root()
    for statement in (
        f"rm -rf {root}\n",
        "rm -rf /srv\n",
        f"rm -rf {root}/*\n",
        f"- name: Drop it\n  ansible.builtin.file:\n    path: {root}\n    state: absent\n",
        f"umount {root}\n",
    ):
        flagged = [
            path for path in _destructive_path_literals(text=statement) if _collides(path=path)
        ]
        assert flagged, (
            f"the destructive-statement reader must flag {statement!r}; it flagged nothing, so "
            f"its silence over the committed tree would mean nothing"
        )
    sibling = "rm -rf /srv/sandbox-storage/containerd\n"
    assert not [
        path for path in _destructive_path_literals(text=sibling) if _collides(path=path)
    ], (
        f"and it must NOT flag {sibling!r}: /srv/sandbox-storage is a real sibling tree "
        f"ansible/roles/sandbox_storage migrates and reclaims, and a reader that flagged it "
        f"would be a reader nobody could keep green"
    )
    assert _collides(path="/"), "the root filesystem is an ancestor of every path"
    assert not _collides(path="/data/projects"), "an unrelated tree is not a collision"


def test_no_committed_converge_or_reclaimer_destroys_the_factory_workspace_root() -> None:
    """The scan itself, over every artifact in the two trees that installs on a node.

    `converge-ci-stack.sh` rebuilds the whole cluster stack on every boot; the
    phase0 recipe lays out a node's storage from empty; `sweep-runner-scratch.sh`
    runs Before= the node's k3s unit and removes local-path volume directories;
    `sandbox_storage` migrates and reclaims a second disk's stores. None of them
    may name the factory workspace root, an ancestor of it, or anything inside
    it, in a statement that removes, empties, reformats or unmounts.
    """
    scanned = _scanned_files()
    for required in _MUST_BE_SCANNED:
        assert required in scanned, (
            f"{required.relative_to(_REPO_ROOT)} must be inside the scanned set; it is not, so "
            f"this scan's silence says nothing about the artifact the work-item names"
        )
    collisions = {
        str(path.relative_to(_REPO_ROOT)): sorted(
            literal
            for literal in _destructive_path_literals(text=path.read_text(encoding="utf-8"))
            if _collides(path=literal)
        )
        for path in scanned
    }
    offenders = {path: literals for path, literals in collisions.items() if literals}
    assert not offenders, (
        f"no boot-time converge, storage sweep or reclaimer in this repository may remove, "
        f"empty or remount {_workspace_root()} — a factory run's workspace would vanish with "
        f"nothing erroring anywhere. Offending statements: {offenders}"
    )


def test_the_workspace_root_is_named_only_where_it_is_declared_documented_or_denied() -> None:
    """Non-naming closes the gap the scan cannot: a path built from a variable.

    A literal reader cannot see `"${root}/factory-workspaces"`, so rather than
    trying, this arm establishes that NO other artifact in either tree names the
    path at all. The four that may: the role's own declaration, the capacity
    record beside it, and the two reclaimers' deny lists. A new mount unit, an
    fstab line or a sweep root naming the path fails here.
    """
    root = _workspace_root()
    naming = {
        str(path.relative_to(_REPO_ROOT))
        for path in _scanned_files()
        if root in path.read_text(encoding="utf-8")
    }
    naming.update(
        str(path.relative_to(_REPO_ROOT))
        for path in (_ROLE_CAPACITY,)
        if root in path.read_text(encoding="utf-8")
    )
    expected = {
        str(_ROLE_DEFAULTS.relative_to(_REPO_ROOT)),
        str(_ROLE_CAPACITY.relative_to(_REPO_ROOT)),
        str(_STORAGE_RECLAIM.relative_to(_REPO_ROOT)),
        str(_CONTAINER_RECLAIM.relative_to(_REPO_ROOT)),
    }
    assert naming == expected, (
        f"{root} must be named only where it is declared, documented or DENIED.\n"
        f"expected: {sorted(expected)}\nnaming:   {sorted(naming)}"
    )


def test_both_reclaimers_a_factory_host_runs_deny_the_workspace_root() -> None:
    """`ansible/fabro-hosts.yml` applies both of these to the factory host itself.

    `storage-reclaim.sh` deletes build artifacts and orphaned worktrees under a
    configured root, and its own comment records the hazard: with a root of
    `/srv`, `/srv/anything` is legitimately under the root and every other guard
    passes. `container-reclaim.sh` never deletes by path but DOES `du` a
    daemon-reported store root. Naming the workspace root in both deny lists
    makes it a root neither may be pointed at by any host variable — the
    mechanical exclusion, rather than a convention about how they are configured.
    """
    root = _workspace_root()
    for script in (_STORAGE_RECLAIM, _CONTAINER_RECLAIM):
        roots = _deny_roots(script=script)
        assert root in roots, (
            f"{script.relative_to(_REPO_ROOT)} must carry {root} in DENY_ROOTS; it declares "
            f"{roots}. `/srv` alone does not cover it: the deny test is an EXACT match, so a "
            f"root of {root} would pass every guard and the reclaim would run inside a live "
            f"factory workspace"
        )
        assert "/srv" in roots, (
            f"and {script.relative_to(_REPO_ROOT)} must keep /srv denied as well — the entry "
            f"this one sits beside, not one it replaces"
        )


def test_the_boot_ordered_scratch_sweep_cannot_reach_the_workspace_root() -> None:
    """The one deleter in this tree that runs at boot, with no operator present.

    `sweep-runner-scratch.sh` removes every local-path volume directory under its
    root Before= the node's k3s unit, and the factory workspace root must be
    outside that root — asserted against the root the script itself defaults to,
    so moving the sweep onto an ancestor of the workspace root fails here rather
    than on a node at 3am.
    """
    assert _SCRATCH_SWEEP.is_file(), f"{_SCRATCH_SWEEP.relative_to(_REPO_ROOT)} must be committed"
    declared = _SWEEP_ROOT.search(_SCRATCH_SWEEP.read_text(encoding="utf-8"))
    assert declared is not None, (
        f"{_SCRATCH_SWEEP.relative_to(_REPO_ROOT)} must default its STORAGE_ROOT in one "
        f'`STORAGE_ROOT="${{STORAGE_ROOT:-<path>}}"` line — the root it sweeps is the fact '
        f"this assertion is about"
    )
    assert not _collides(path=declared["root"]), (
        f"the boot-ordered sweep's root is {declared['root']!r}, which is in a prefix "
        f"relationship with {_workspace_root()}: the sweep runs with no operator present and "
        f"would take a live factory workspace with it"
    )
