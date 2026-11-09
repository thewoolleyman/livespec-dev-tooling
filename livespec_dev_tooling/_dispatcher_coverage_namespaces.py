"""Coverage-namespace isolation for every runner of check targets.

Moved out of `parallel_check_dispatcher` unchanged (work-item
livespec-dev-tooling-cmn's namespace assignment) so that module stays under the
logical-line ceiling. Each coverage-touching target maps to a namespace key; the
runner mints one isolated temp dir per distinct key and exports it to the
target's `just` subprocess as COVERAGE_FILE and TMPDIR.

The expedited incident paths use the same isolation and the same data
dependency through `isolated_environments` and `COVERAGE_CONSUMERS`, so a
coverage-touching target runs alike whichever path selected it
(livespec-dev-tooling-oqpw6t).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

__all__: list[str] = [
    "COVERAGE_CONSUMERS",
    "COVERAGE_NAMESPACES",
    "build_namespace_dirs",
    "isolated_environments",
    "target_env",
]

COVERAGE_NAMESPACES: dict[str, str] = {
    # The full-tree coverage pair shares one data file: per-file-coverage
    # PRODUCES it (runs `pytest -n auto --cov`), check-coverage CONSUMES
    # it (runs `coverage report` against the same file). Same namespace ->
    # same isolated COVERAGE_FILE.
    "check-per-file-coverage": "full-tree",
    "check-coverage": "full-tree",
    # The path-scoped incremental gate runs its OWN coverage-instrumented
    # pytest. Its own namespace isolates its data file from the full-tree
    # pair's `coverage combine`, so it no longer needs to be serialized
    # after per-file-coverage (the retired 7us.6 collision edge).
    "check-check-coverage-incremental": "incremental",
}

# Genuine read-after-write DATA dependencies (consumer -> producer). The
# consumer reads the producer's isolated COVERAGE_FILE, so it must start only
# after the producer has finished writing it. This is the ONLY ordering edge
# that survives the isolation redesign; it is data flow, not collision
# avoidance. Both endpoints MUST share a namespace in COVERAGE_NAMESPACES.
COVERAGE_CONSUMERS: dict[str, str] = {
    "check-coverage": "check-per-file-coverage",
}


def build_namespace_dirs(
    *, targets: list[str], skip_set: frozenset[str], root: Path
) -> dict[str, Path]:
    """Mint one isolated coverage dir per distinct namespace key in play.

    Walks the non-skipped targets, collects the distinct namespace keys
    they map to via `COVERAGE_NAMESPACES`, and creates one fresh temp
    directory per key under `root` (each with a `tmp/` subdir for the
    target's TMPDIR). Returns a key -> dir mapping. Targets that share a
    key (the producer/consumer coverage pair) resolve to the same dir, so
    the consumer reads the producer's COVERAGE_FILE; targets with
    distinct keys get separate dirs and can never erase each other's
    data via `coverage combine`.

    `root` MUST be OUTSIDE the governed repo (the system temp dir): the
    per-target TMPDIR points into these dirs, and pytest's `tmp_path`
    fixture derives from TMPDIR — a TMPDIR inside the repo's git worktree
    breaks tests that assume `tmp_path` is not within any git repo.
    """
    keys = {
        COVERAGE_NAMESPACES[name]
        for name in targets
        if name not in skip_set and name in COVERAGE_NAMESPACES
    }
    dirs: dict[str, Path] = {}
    for key in sorted(keys):
        ns_dir = Path(tempfile.mkdtemp(prefix=f"covns-{key}-", dir=str(root)))
        (ns_dir / "tmp").mkdir(exist_ok=True)
        dirs[key] = ns_dir
    return dirs


def target_env(
    *, name: str, namespace_dirs: dict[str, Path], base: Mapping[str, str] | None = None
) -> dict[str, str] | None:
    """Return the isolated env for a coverage-touching target, else None.

    For a target mapped to a coverage namespace, returns a COPY of `base`
    (the process environment when None) with COVERAGE_FILE pointed at
    `<ns_dir>/.coverage`
    and TMPDIR pointed at `<ns_dir>/tmp`. A COVERAGE_PROCESS_START child
    spawned by the target inherits this COVERAGE_FILE, so its data lands
    in the same isolated dir. Returns None for non-coverage targets (the
    subprocess then inherits the parent env unchanged).

    It also exports LIVESPEC_COVERAGE_WRITERS: every coverage-touching
    target whose namespace is in play in this aggregate, so
    per_file_coverage's unreadable-data diagnostic names each process that
    could have written coverage in the run (work-item
    livespec-dev-tooling-3wz453).
    """
    key = COVERAGE_NAMESPACES.get(name)
    if key is None:
        return None
    ns_dir = namespace_dirs[key]
    env = dict(os.environ if base is None else base)
    env["COVERAGE_FILE"] = str(ns_dir / ".coverage")
    env["TMPDIR"] = str(ns_dir / "tmp")
    writers = sorted(target for target, ns in COVERAGE_NAMESPACES.items() if ns in namespace_dirs)
    env["LIVESPEC_COVERAGE_WRITERS"] = ", ".join(writers)
    return env


@contextmanager
def isolated_environments(
    *, names: Sequence[str], base: Mapping[str, str] | None
) -> Iterator[dict[str, dict[str, str] | None]]:
    """Mint the namespace dirs `names` need, yield each name's env, then remove them.

    A coverage-touching target gets its isolated overlay of `base`; any other
    target gets `base` itself, or None (inherit the caller's environment) when
    `base` is None. The dirs live in the system temp dir, OUTSIDE the governed
    repo: pytest's `tmp_path` derives from the per-target TMPDIR, and a TMPDIR
    inside the repo's git worktree breaks tests that assume `tmp_path` is not in
    a repo. Removal is best-effort, so a transient failure never masks a result.
    """
    namespace_dirs = build_namespace_dirs(
        targets=list(names), skip_set=frozenset(), root=Path(tempfile.gettempdir())
    )
    try:
        yield {
            name: target_env(name=name, namespace_dirs=namespace_dirs, base=base)
            or (None if base is None else dict(base))
            for name in names
        }
    finally:
        for ns_dir in namespace_dirs.values():
            shutil.rmtree(ns_dir, ignore_errors=True)
