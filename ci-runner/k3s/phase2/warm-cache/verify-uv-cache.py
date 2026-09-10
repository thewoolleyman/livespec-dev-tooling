#!/usr/bin/env python3
"""verify-uv-cache.py — map every entry of a uv 0.9.x cache back to a
(package name, version) and report any entry not referenced by the union of
the given uv.lock files.

The warm-cache populator (warm-cache-populate.sh) runs this over every
generation it builds, BEFORE publishing it: a generation with an entry that no
routed lockfile references is not published, and the entries are named here.
It is the mechanical half of the "nothing useless in it" rule from the
livespec plan `ci-runner-pod-lifecycle-reliability` (item livespec-41w4); the
design and the cache-layout table it encodes are in README.md "Verifier". The
layout knowledge itself is uv_cache_layout.py beside this file; this file is
the CLI and the report.

Stdlib (tomllib needs Python >= 3.11 — the fabro sandbox image's CPython and
the CI host's both qualify) PLUS `returns`: every public function here and in
the layout half that can fail rides the Result/IOResult railway livespec's
`SPECIFICATION/non-functional-requirements.md` section "ROP composition" binds
all first-party Python to (maintainer ruling 2026-09-10,
livespec-dev-tooling-qndn.1). `warm-cache-populate.sh` makes `returns`
importable before invoking this script — its header, "THE VERIFIER'S RAILWAY".
Shipped to the populator pod as keys of the `warm-cache-populate` ConfigMap
(converge-warm-cache.sh), mounted at /scripts, which is why the sibling import
below needs no packaging.

usage: verify-uv-cache.py --cache DIR [--allow NAME,NAME] [--json] [LOCK ...]
exit 0 = every entry referenced; exit 1 = unreferenced or unknown entries;
exit 2 = usage / unreadable input — WHICH IS NOW WHERE EVERY IO FAILURE LANDS.
Before the railway conversion an unreadable lock or a vanishing generation
raised, and CPython exits 1 on an uncaught exception, so the populator read a
crash as the "unreferenced entries" verdict and kept the previous generation
for the wrong reason. Each `main()` guard below maps its failure track to 2,
the code the populator already treats as "did not run to a verdict".

Build dependencies are the one legitimate class outside every lock (hatchling,
setuptools, ...): derived from `[build-system].requires` of every source tree
uv built (sdists and git checkouts; PEP 517 default setuptools+wheel when
absent), closed over the `Requires-Dist` of the unpacked wheels — no
allowlist, reported as their own class. `--allow` exists for a hand run only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

import tomllib
from returns.io import IOResult, impure_safe
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io
from uv_cache_layout import (
    Classifier,
    Entry,
    archive_index_of,
    du,
    load_locks,
    norm,
    scan_cache,
)

__all__: list[str] = []

REQ_SPLIT_RE = re.compile(r"[\s<>=!~;\[(@]")
PEP517_DEFAULT_BUILD_DEPS = frozenset({"setuptools", "wheel"})
EXIT_OK = 0
EXIT_UNREFERENCED = 1
EXIT_USAGE = 2


def req_name(*, req: str) -> str:
    """The normalized project name at the head of a PEP 508 requirement."""
    return norm(name=REQ_SPLIT_RE.split(req.strip(), maxsplit=1)[0])


def _build_seeds_of(*, pyproject: Path) -> set[str]:
    try:
        with pyproject.open("rb") as fh:
            data = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError):
        return set()
    reqs = data.get("build-system", {}).get("requires")
    if reqs is None:
        return set(PEP517_DEFAULT_BUILD_DEPS)
    return {req_name(req=r) for r in reqs}


@impure_safe(exceptions=(OSError,))
def build_dep_seeds(*, cache: Path) -> set[str]:
    """The `[build-system].requires` names of every source tree uv built here,
    as `IOResult[set[str], OSError]` — globbing a generation the populator may
    still be writing is an expected failure of this input, not a bug."""
    seeds: set[str] = set()
    src_roots = [*cache.glob("sdists-v9/*/*/*/*/src"), *cache.glob("git-v0/checkouts/*/*")]
    for root in src_roots:
        pyprojects = [
            p for p in [root / "pyproject.toml", *root.glob("*/pyproject.toml")] if p.is_file()
        ]
        if not pyprojects:
            seeds.update(PEP517_DEFAULT_BUILD_DEPS)
            continue
        for pyproject in pyprojects:
            seeds.update(_build_seeds_of(pyproject=pyproject))
    return seeds


def _requires_dist_of(*, archive_dir: Path) -> Iterator[str]:
    for meta in archive_dir.glob("*.dist-info/METADATA"):
        with meta.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.startswith("Requires-Dist:") and "extra ==" not in line:
                    yield req_name(req=line.split(":", 1)[1])


@impure_safe(exceptions=(OSError,))
def _closed_over_requires_dist(
    *, seeds: set[str], archive_index: dict[str, list[Path]]
) -> set[str]:
    """`seeds` closed over the `Requires-Dist` of the archive-v0 wheels they
    reach. The METADATA-reading half of `build_dep_closure`, lifted on its own
    so the closure can be a `bind` over the seeds rather than a second reader
    of the cache."""
    closure: set[str] = set()
    todo = list(seeds)
    while todo:
        name = todo.pop()
        if name in closure:
            continue
        closure.add(name)
        for archive_dir in archive_index.get(name, []):
            todo.extend(_requires_dist_of(archive_dir=archive_dir))
    return closure


def build_dep_closure(
    *, cache: Path, archive_index: dict[str, list[Path]]
) -> IOResult[set[str], OSError]:
    """Names a from-empty build legitimately fetched WITHOUT a lock entry: the
    build-system requirements of every source tree uv built, closed over the
    Requires-Dist of the unpacked wheels in archive-v0."""
    return build_dep_seeds(cache=cache).bind(
        lambda seeds: _closed_over_requires_dist(seeds=seeds, archive_index=archive_index)
    )


def _totals(entries: list[Entry]) -> dict[str, int]:
    return {
        "entries": len(entries),
        "bytes": sum(e.size_bytes for e in entries),
        "files": sum(e.files for e in entries),
    }


def summarize(
    *, cache: Path, locks: list[str], c: Classifier, generation: tuple[int, int]
) -> dict[str, object]:
    """The report document, over ALREADY-MEASURED in-memory state.

    `generation` is `du(path=cache)`'s `(bytes, files)`, taken and unwrapped by
    `main()`. Passing it in rather than measuring here is what keeps this a
    pure transform with no expected failure mode of its own — the shape the
    railway rule's own member-1 exemption is for — instead of a third caller
    that would have to carry a container just to render a dict.
    """
    total_bytes, total_files = generation
    return {
        "cache": str(cache),
        "locks": locks,
        "lock_pairs": len(c.union.pairs),
        "generation_bytes": total_bytes,
        "generation_files": total_files,
        "referenced": _totals(c.ok),
        "build_deps": {**_totals(c.build), "names": sorted({e.name for e in c.build if e.name})},
        "unreferenced": [
            {
                "bucket": e.bucket,
                "entry": e.rel,
                "name": e.name,
                "version": e.version,
                "bytes": e.size_bytes,
                "files": e.files,
            }
            for e in c.bad
        ],
        "unknown": [
            {"bucket": e.bucket, "entry": e.rel, "bytes": e.size_bytes, "files": e.files}
            for e in c.unknown
        ],
    }


def render_text(*, summary: dict[str, object], c: Classifier, lock_count: int) -> str:
    ref = _totals(c.ok)
    build = _totals(c.build)
    lines = [
        f"generation: {summary['generation_bytes']} bytes, {summary['generation_files']} files; "
        f"lock union: {len(c.union.pairs)} (name,version) pairs from {lock_count} lock(s)",
        f"referenced: {ref['entries']} entries, {ref['bytes']} bytes, {ref['files']} files",
        f"build-deps (derived from [build-system].requires closure): {build['entries']} entries, "
        f"{build['bytes']} bytes, {build['files']} files: "
        + " ".join(sorted({e.name for e in c.build if e.name})),
    ]
    lines.extend(
        f"UNREFERENCED {e.bucket}/{e.rel} -> ({e.name}, {e.version}) "
        f"{e.size_bytes} bytes {e.files} files"
        for e in c.bad
    )
    lines.extend(
        f"UNKNOWN {e.bucket}/{e.rel} {e.size_bytes} bytes {e.files} files" for e in c.unknown
    )
    return "\n".join(lines) + "\n"


def _fatal(*, what: str, failed: IOResult[object, Exception]) -> int:
    """Report `failed`'s exception on the "unreadable input" exit path.

    ONE reporter for every railway guard in `main()`, so no guard can drift
    into a different exit code: an IO failure is never a verdict about the
    generation, and EXIT_USAGE is the one code the populator does not read as
    one.
    """
    sys.stderr.write(f"FATAL: {what}: {unsafe_perform_io(failed.failure())}\n")
    return EXIT_USAGE


def _classifier_for(
    *, cache: Path, allow: str, locks: list[str]
) -> IOResult[Classifier, Exception]:
    """The classifier this run needs, composed from the three IO reads it takes.

    Composed with `bind`/`map` rather than unwrapped step by step: the three
    reads are all inputs to ONE object, so there is nothing for `main()` to do
    between them but propagate, and the first failure short-circuits the rest.
    """
    return load_locks(paths=locks).bind(
        lambda union: archive_index_of(cache=cache).bind(
            lambda index: build_dep_closure(cache=cache, archive_index=index).map(
                lambda build_names: Classifier(
                    union=union,
                    allow={norm(name=x) for x in allow.split(",") if x},
                    build_names=build_names,
                )
            )
        )
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--allow", default="", help="comma-separated names allowed at any version")
    ap.add_argument("--json", action="store_true")
    # Zero locks is a legal union (no routed repository has a uv.lock): every
    # package entry is then unreferenced, and only an empty cache passes.
    ap.add_argument("locks", nargs="*")
    args = ap.parse_args()
    cache = Path(args.cache)
    if not cache.is_dir():
        sys.stderr.write(f"FATAL: {cache} is not a directory\n")
        return EXIT_USAGE
    built = _classifier_for(cache=cache, allow=args.allow, locks=args.locks)
    if not is_successful(built):
        return _fatal(what="reading the verifier's inputs", failed=built)
    c = unsafe_perform_io(built.unwrap())
    scanned = scan_cache(cache=cache, c=c)
    if not is_successful(scanned):
        return _fatal(what=f"scanning {cache}", failed=scanned)
    measured = du(path=cache)
    if not is_successful(measured):
        return _fatal(what=f"measuring {cache}", failed=measured)
    summary = summarize(
        cache=cache, locks=args.locks, c=c, generation=unsafe_perform_io(measured.unwrap())
    )
    if args.json:
        sys.stdout.write(json.dumps(summary, indent=1) + "\n")
    else:
        sys.stdout.write(render_text(summary=summary, c=c, lock_count=len(args.locks)))
    return EXIT_UNREFERENCED if (c.bad or c.unknown) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
