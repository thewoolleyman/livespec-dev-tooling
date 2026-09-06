"""uv_cache_layout — the uv 0.9.x cache layout, as a mapping from every entry
back to a (package name, version), and the lock-union it is checked against.

The knowledge half of verify-uv-cache.py (the CLI half imports this from
its own directory — both are keys of the `warm-cache-populate` ConfigMap,
mounted together at /scripts). Encodes the bucket table in README.md
"Verifier": archive-v0, wheels-v5, sdists-v9, git-v0, simple-v18, plus the
build-dependency closure that is the one legitimate class outside every
lock. stdlib only.
"""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

__all__ = [
    "BUCKETS",
    "TOP_FILES",
    "Classifier",
    "Entry",
    "LockUnion",
    "archive_index_of",
    "du",
    "load_locks",
    "norm",
    "scan_cache",
]


# The top-level buckets uv 0.9.x writes; anything else at the top level is
# UNKNOWN (and fails the publish) so a layout change in a uv bump is caught
# here rather than silently seeded into every job.
BUCKETS = frozenset(
    {"archive-v0", "wheels-v5", "sdists-v9", "git-v0", "simple-v18", "interpreter-v4", "builds-v0"}
)
# uv's own top-level files, plus the populator's per-generation manifest.
TOP_FILES = frozenset({".lock", ".gitignore", "CACHEDIR.TAG", ".warm-manifest.json"})
POINTER_SUFFIX_RE = re.compile(r"\.(http|msgpack|rev|lock)$")
SIMPLE_SUFFIX_RE = re.compile(r"\.(rkyv|msgpack|http)$")


def norm(*, name: str) -> str:
    """PEP 503 normalization: runs of `-_.` collapse to `-`, lowercase."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(kw_only=True)
class LockUnion:
    """What the union of the lockfiles references."""

    pairs: set[tuple[str, str]] = field(default_factory=set)
    names: set[str] = field(default_factory=set)
    git_shas: set[str] = field(default_factory=set)

    def references_git_sha(self, *, prefix: str) -> bool:
        return any(sha.startswith(prefix) for sha in self.git_shas)


def load_locks(*, paths: Iterable[str]) -> LockUnion:
    union = LockUnion()
    for path in paths:
        with Path(path).open("rb") as fh:
            lock = tomllib.load(fh)
        for pkg in lock.get("package", []):
            name, version = norm(name=pkg["name"]), pkg.get("version")
            src = pkg.get("source", {})
            if "git" in src and "#" in src["git"]:
                union.git_shas.add(src["git"].split("#", 1)[1])
            if "virtual" in src or "editable" in src:
                continue  # the project itself; never in the cache
            union.names.add(name)
            if version is not None:
                union.pairs.add((name, version))
    return union


def du(*, path: Path) -> tuple[int, int]:
    """(bytes, regular files) under `path`, symlinks counted by their own size."""
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size, 1
    total, files = 0, 0
    for child in path.rglob("*"):
        # Directories, and symlinks TO directories (uv's wheels-v5 pointers),
        # are not files — the same count `find -type f` gives the populator.
        if child.is_dir():
            continue
        with contextlib.suppress(FileNotFoundError):
            total += child.lstat().st_size
            files += 1
    return total, files


def dist_info_of(*, archive_dir: Path) -> tuple[str, str] | None:
    """(name, version) from the `<Name>-<Version>.dist-info` of an unpacked wheel."""
    for child in archive_dir.iterdir():
        if child.name.endswith(".dist-info"):
            stem = child.name[: -len(".dist-info")]
            name, _, version = stem.rpartition("-")
            return norm(name=name), version
    return None


@dataclass(frozen=True, kw_only=True)
class Entry:
    bucket: str
    rel: str
    name: str | None
    version: str | None
    size_bytes: int
    files: int


@dataclass(kw_only=True)
class Classifier:
    union: LockUnion
    allow: set[str]
    build_names: set[str]
    ok: list[Entry] = field(default_factory=list)
    build: list[Entry] = field(default_factory=list)
    bad: list[Entry] = field(default_factory=list)
    unknown: list[Entry] = field(default_factory=list)

    def add(self, *, bucket: str, rel: str, nv: tuple[str | None, str | None], path: Path) -> None:
        name, version = nv
        size_bytes, files = du(path=path)
        entry = Entry(
            bucket=bucket, rel=rel, name=name, version=version, size_bytes=size_bytes, files=files
        )
        if name is None:
            self.unknown.append(entry)
        elif self._referenced(name=name, version=version):
            self.ok.append(entry)
        elif name in self.build_names:
            self.build.append(entry)
        else:
            self.bad.append(entry)

    def _referenced(self, *, name: str, version: str | None) -> bool:
        if version is None:
            return name in self.union.names or name in self.allow
        return (name, version) in self.union.pairs or name in self.allow


def _index_dirs(*, top: Path) -> Iterator[tuple[str, Path]]:
    """`(label, dir)` per index under a bucket: `pypi/` and friends are one level;
    a non-PyPI index is `index/<url-hash>/`, one level deeper."""
    for index in top.iterdir():
        if index.name == "index":
            for idx in index.iterdir():
                yield f"{index.name}/{idx.name}", idx
        else:
            yield index.name, index


def scan_archive(*, top: Path, c: Classifier) -> None:
    for child in top.iterdir():
        nv = dist_info_of(archive_dir=child) if child.is_dir() else None
        c.add(bucket="archive-v0", rel=child.name, nv=nv or (None, None), path=child)


def scan_wheels(*, top: Path, c: Classifier) -> None:
    for label, idx in _index_dirs(top=top):
        for pkg in idx.iterdir():
            for entry in pkg.iterdir():
                # "<version>-<py>-<abi>-<plat>[.http|.msgpack]"; the version is
                # the first `-` field of the stem.
                version = POINTER_SUFFIX_RE.sub("", entry.name).split("-")[0]
                nv = (norm(name=pkg.name), version)
                c.add(bucket="wheels-v5", rel=f"{label}/{pkg.name}/{entry.name}", nv=nv, path=entry)


def _scan_sdists_git(*, kind: Path, c: Classifier) -> None:
    for urlhash in kind.iterdir():
        for sha in urlhash.iterdir():
            nv: tuple[str | None, str | None] = (None, None)
            for e in sha.iterdir():
                if e.suffix == ".whl":
                    parts = e.stem.split("-")
                    nv = (norm(name=parts[0]), parts[1])
            if nv[0] is not None and not c.union.references_git_sha(prefix=sha.name):
                nv = (nv[0], f"{nv[1]}@{sha.name}(not a locked git sha)")
            c.add(bucket="sdists-v9/git", rel=f"{urlhash.name}/{sha.name}", nv=nv, path=sha)


def scan_sdists(*, top: Path, c: Classifier) -> None:
    for kind in top.iterdir():
        if kind.name in (".git", ".gitignore"):
            continue
        if kind.name == "git":
            _scan_sdists_git(kind=kind, c=c)
            continue
        for pkg in kind.iterdir():  # pypi / other index / url / path: <name>/<version>/...
            for ver in kind.joinpath(pkg.name).iterdir():
                nv = (norm(name=pkg.name), ver.name)
                c.add(
                    bucket=f"sdists-v9/{kind.name}", rel=f"{pkg.name}/{ver.name}", nv=nv, path=ver
                )


def _git_db_has_locked_sha(*, gitdir: Path, shas: Iterable[str]) -> bool:
    git = shutil.which("git")
    # S603: argv is a fixed list; the sha comes from a lockfile we read.
    return git is not None and any(
        subprocess.run(  # noqa: S603
            [git, "--git-dir", str(gitdir), "cat-file", "-e", sha], capture_output=True, check=False
        ).returncode
        == 0
        for sha in shas
    )


def _git_kinds(*, top: Path) -> list[Path]:
    """db and checkouts BEFORE locks, whatever order the directory lists them.

    A lock file under git-v0/locks/<urlhash> is referenced iff the same
    urlhash's db or checkout matched a locked sha, which is only known after
    those two kinds were scanned. iterdir() order is arbitrary: on the first
    live from-empty build (2026-09-06) `locks` came first and the verifier
    rejected a correct generation on two zero-byte lock files.
    """
    rank = {"db": 0, "checkouts": 1, "locks": 2}
    return sorted(top.iterdir(), key=lambda k: (rank.get(k.name, 3), k.name))


def scan_git(*, top: Path, c: Classifier) -> None:
    for kind in _git_kinds(top=top):  # db, checkouts, then locks
        for urlhash in kind.iterdir():
            label = f"git:{urlhash.name}"
            if kind.name == "checkouts":
                for sha in urlhash.iterdir():
                    hit = c.union.references_git_sha(prefix=sha.name)
                    if hit:
                        c.union.names.add(label)
                    nv = (label if hit else None, None)
                    c.add(
                        bucket="git-v0/checkouts", rel=f"{urlhash.name}/{sha.name}", nv=nv, path=sha
                    )
            elif kind.name == "db":
                hit = _git_db_has_locked_sha(gitdir=urlhash / ".git", shas=c.union.git_shas)
                if hit:
                    c.union.names.add(label)
                c.add(
                    bucket="git-v0/db",
                    rel=urlhash.name,
                    nv=(label if hit else None, None),
                    path=urlhash,
                )
            else:
                c.add(bucket="git-v0/locks", rel=urlhash.name, nv=(label, None), path=urlhash)


def scan_simple(*, top: Path, c: Classifier) -> None:
    for label, idx in _index_dirs(top=top):
        for entry in idx.iterdir():
            name = norm(name=SIMPLE_SUFFIX_RE.sub("", entry.name))
            c.add(bucket="simple-v18", rel=f"{label}/{entry.name}", nv=(name, None), path=entry)


# Static dispatch, one scanner per package bucket; `interpreter-v4` holds
# interpreter probes, not packages, and is counted in the totals only.
SCANNERS: dict[str, Callable[..., None]] = {
    "archive-v0": scan_archive,
    "wheels-v5": scan_wheels,
    "sdists-v9": scan_sdists,
    "git-v0": scan_git,
    "simple-v18": scan_simple,
}


def scan_cache(*, cache: Path, c: Classifier) -> None:
    for top in sorted(cache.iterdir()):
        if top.name in TOP_FILES or top.name == "interpreter-v4":
            continue
        if top.name not in BUCKETS:
            c.add(bucket="<top>", rel=top.name, nv=(None, None), path=top)
        elif top.name == "builds-v0":
            for child in top.iterdir():
                c.add(bucket="builds-v0", rel=child.name, nv=(None, None), path=child)
        else:
            SCANNERS[top.name](top=top, c=c)


def archive_index_of(*, cache: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    arch = cache / "archive-v0"
    if arch.is_dir():
        for child in arch.iterdir():
            nv = dist_info_of(archive_dir=child) if child.is_dir() else None
            if nv:
                index.setdefault(nv[0], []).append(child)
    return index
