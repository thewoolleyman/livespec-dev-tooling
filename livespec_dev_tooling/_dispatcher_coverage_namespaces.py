"""Coverage-namespace isolation for the parallel check dispatcher.

Moved out of `parallel_check_dispatcher` unchanged (work-item
livespec-dev-tooling-cmn's namespace assignment) so that module stays under the
logical-line ceiling. Each coverage-touching target maps to a namespace key; the
dispatcher mints one isolated temp dir per distinct key and exports it to the
target's `just` subprocess as COVERAGE_FILE and TMPDIR.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__: list[str] = ["COVERAGE_NAMESPACES", "build_namespace_dirs", "target_env"]

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


def target_env(*, name: str, namespace_dirs: dict[str, Path]) -> dict[str, str] | None:
    """Return the isolated env for a coverage-touching target, else None.

    For a target mapped to a coverage namespace, returns a COPY of the
    process environment with COVERAGE_FILE pointed at `<ns_dir>/.coverage`
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
    env = dict(os.environ)
    env["COVERAGE_FILE"] = str(ns_dir / ".coverage")
    env["TMPDIR"] = str(ns_dir / "tmp")
    writers = sorted(target for target, ns in COVERAGE_NAMESPACES.items() if ns in namespace_dirs)
    env["LIVESPEC_COVERAGE_WRITERS"] = ", ".join(writers)
    return env
