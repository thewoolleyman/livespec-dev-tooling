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

import json
import logging
import os
import re
import shutil
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, TypeGuard

from livespec_dev_tooling._check_target_isolation import termination_raises

__all__: list[str] = [
    "COVERAGE_CONSUMERS",
    "COVERAGE_NAMESPACES",
    "build_namespace_dirs",
    "isolated_environments",
    "process_start_time",
    "reclaim_abandoned_namespace_dirs",
    "target_env",
]

_CREATOR_RECORD_NAME = ".livespec-coverage-creator.json"
_UNRECORDED_NAMESPACE_MAX_AGE_SECONDS = 24 * 60 * 60
# /proc/<pid>/stat is `pid (comm) state` followed by integer fields up to the
# start time, which is the 20th field after the state.
_STAT_HEAD = re.compile(r"\d+ \(")
_STAT_TAIL = re.compile(r" [A-Za-z](?: -?\d+){18} (\d+)(?=\s|\Z)")
_LOGGER = logging.getLogger(__name__)

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


def _parse_start_time(*, stat: str) -> str | None:
    closing_parenthesis = stat.rfind(")")
    if closing_parenthesis < 0 or _STAT_HEAD.match(stat[:closing_parenthesis]) is None:
        return None
    tail = _STAT_TAIL.match(stat, closing_parenthesis + 1)
    return None if tail is None else tail.group(1)


def process_start_time(*, pid: int) -> str | None:
    """Return Linux's immutable start-time tick for `pid`, if it is observable."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_start_time(stat=stat)


def _is_string_keyed_dict(*, value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _creator_identity(
    *, namespace_dir: Path
) -> tuple[Literal["absent", "unreadable", "malformed", "valid"], tuple[int, str] | None]:
    record = namespace_dir / _CREATOR_RECORD_NAME
    try:
        loaded: object = json.loads(record.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return "absent", None
    except OSError as error:
        _LOGGER.warning("could not read creator record %s: %s", record, error)
        return "unreadable", None
    except json.JSONDecodeError as error:
        _LOGGER.warning("malformed creator record %s: %s", record, error)
        return "malformed", None
    if not _is_string_keyed_dict(value=loaded):
        _LOGGER.warning("malformed creator record %s: expected an object", record)
        return "malformed", None
    pid = loaded.get("pid")
    start_time = loaded.get("start_time")
    if (
        not isinstance(pid, int)
        or isinstance(pid, bool)
        or pid <= 0
        or not isinstance(start_time, str)
        or not start_time
    ):
        _LOGGER.warning("malformed creator record %s: invalid pid or start time", record)
        return "malformed", None
    return "valid", (pid, start_time)


def _creator_is_gone(*, pid: int, start_time: str) -> bool:
    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        observed = proc_stat.read_text(encoding="utf-8")
    except FileNotFoundError:
        return True
    except OSError as error:
        _LOGGER.warning("could not observe coverage creator %s: %s", proc_stat, error)
        return False
    observed_start_time = _parse_start_time(stat=observed)
    if observed_start_time is None:
        _LOGGER.warning("could not observe coverage creator %s: invalid stat data", proc_stat)
        return False
    return observed_start_time != start_time


def _remove_abandoned_namespace(*, namespace_dir: Path) -> None:
    try:
        shutil.rmtree(namespace_dir)
    except FileNotFoundError:
        return
    except OSError as error:
        _LOGGER.warning(
            "could not remove abandoned coverage namespace %s: %s", namespace_dir, error
        )


def reclaim_abandoned_namespace_dirs(*, root: Path) -> None:
    """Best-effort reclaim dead-recorded and old-unrecorded coverage namespaces."""
    for namespace_dir in root.glob("covns-*"):
        state, creator = _creator_identity(namespace_dir=namespace_dir)
        try:
            metadata = namespace_dir.stat()
        except OSError as error:
            if isinstance(error, FileNotFoundError):
                continue
            _LOGGER.warning("could not stat coverage namespace %s: %s", namespace_dir, error)
            continue
        if not namespace_dir.is_dir():
            continue
        if state == "absent":
            if time.time() - metadata.st_mtime > _UNRECORDED_NAMESPACE_MAX_AGE_SECONDS:
                _remove_abandoned_namespace(namespace_dir=namespace_dir)
            continue
        if (
            state == "valid"
            and creator is not None
            and _creator_is_gone(pid=creator[0], start_time=creator[1])
        ):
            _remove_abandoned_namespace(namespace_dir=namespace_dir)


def _record_creator(*, namespace_dir: Path) -> None:
    pid = os.getpid()
    start_time = process_start_time(pid=pid)
    if pid <= 0 or start_time is None:
        _LOGGER.warning(
            "could not observe this runner's start time; %s records no creator", namespace_dir
        )
        return
    try:
        _ = (namespace_dir / _CREATOR_RECORD_NAME).write_text(
            json.dumps({"pid": pid, "start_time": start_time}), encoding="utf-8"
        )
    except OSError as error:
        _LOGGER.warning("could not record coverage creator %s: %s", namespace_dir, error)


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
    reclaim_abandoned_namespace_dirs(root=root)
    keys = {
        COVERAGE_NAMESPACES[name]
        for name in targets
        if name not in skip_set and name in COVERAGE_NAMESPACES
    }
    dirs: dict[str, Path] = {}
    for key in sorted(keys):
        ns_dir = Path(tempfile.mkdtemp(prefix=f"covns-{key}-", dir=str(root)))
        _record_creator(namespace_dir=ns_dir)
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
    SIGTERM and SIGHUP received meanwhile are turned into a non-zero `SystemExit`
    (a signal the caller ignores stays ignored), so the dirs are removed on the
    way out.
    """
    # SIGTERM and SIGHUP raise `SystemExit` for the whole life of the dirs, so the
    # `finally` below runs when the gate runner's stall kill, a lefthook hangup or
    # a harness kill ends the run, instead of leaking one dir per namespace
    # (livespec-dev-tooling-8o8e.16). SIGKILL cannot be caught and is outside this.
    with termination_raises(isolated=True):
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
