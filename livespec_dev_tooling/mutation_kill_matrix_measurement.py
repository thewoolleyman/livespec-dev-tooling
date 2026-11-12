"""The Rule-26 kill matrix's stored baseline measurement: reuse it while nothing moved.

Measuring per-test coverage runs the target's whole suite once, serially.
For a large target that is hours (about 3.6 h for the orchestrator on run
20261111t1), and a run resumed from the result cache used to repeat it before
it could compute a single cache key.  The measurement is therefore stored
beside the result cache, keyed by everything the baseline run can depend on:
the engine, Python and dependency versions, the per-test timeout, every input
file of the tree (see `mutation_kill_matrix_cache.tree_files`) and the
collected tests.  A run whose key matches reuses the stored coverage and
baseline failures and skips the measure stage; anything else measures again.

A run in which coverage could not be measured stores nothing, so a transient
failure is never reused.  The stored form names each test and each distinct
set of tests once, because thousands of lines share the same tests.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import cast

from livespec_dev_tooling.mutation_kill_matrix_cache import tree_files
from livespec_dev_tooling.mutation_kill_matrix_cache_store import write_whole
from livespec_dev_tooling.mutation_kill_matrix_execution import CommandExecutor
from livespec_dev_tooling.mutation_kill_matrix_selection import PerTestCoverage

__all__: list[str] = [
    "MEASUREMENT_SCHEMA",
    "Measurement",
    "load_measurement",
    "measurement_key",
    "measurement_path",
    "reuse_or_measure",
    "save_measurement",
]


MEASUREMENT_SCHEMA = "rule-26-kill-matrix-measurement/1"
_REUSED = (
    "mutation-kill-matrix: reused the stored per-test coverage; the measure stage is skipped\n"
)


@dataclass(frozen=True, kw_only=True)
class Measurement:
    """What one baseline run measured: per-test coverage and the baseline failures."""

    coverage: PerTestCoverage | None
    baseline_failures: frozenset[str]


def measurement_path(*, cache_path: Path | None) -> Path | None:
    """Name the stored measurement beside the result cache; a run without a cache has none."""
    return None if cache_path is None else cache_path.with_name(cache_path.stem + "-measure.json")


def measurement_key(
    *,
    target: Path,
    tests: list[str],
    engine_version: str,
    timeout: float,
    execute: CommandExecutor,
) -> str:
    """Digest everything the baseline run can depend on."""
    parts = [
        MEASUREMENT_SCHEMA,
        engine_version,
        platform.python_version(),
        repr(timeout),
        *sorted({f"{dist.metadata['Name']}=={dist.version}" for dist in metadata.distributions()}),
        *(
            f"{relative.as_posix()}:{hashlib.sha256((target / relative).read_bytes()).hexdigest()}"
            for relative in tree_files(target=target, execute=execute)
        ),
        "tests",
        *tests,
    ]
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()


def _stored_coverage(*, document: dict[str, object]) -> PerTestCoverage:
    """Rebuild the coverage map from its interned form."""
    tests = cast("list[str]", document["tests"])
    sets = [
        frozenset(tests[index] for index in indexes)
        for indexes in cast("list[list[int]]", document["sets"])
    ]
    files = cast("dict[str, dict[str, int]]", document["coverage"])
    return {
        path: {int(line): sets[index] for line, index in lines.items()}
        for path, lines in files.items()
    }


def load_measurement(*, path: Path | None, key: str) -> Measurement | None:
    """Load the stored measurement when it is readable and was taken under this key."""
    if path is None or not path.is_file():
        return None
    try:
        loaded: object = json.loads(path.read_text(encoding="utf-8"))
        document = cast("dict[str, object]", loaded)
        if document["schema"] != MEASUREMENT_SCHEMA or document["key"] != key:
            return None
        return Measurement(
            coverage=_stored_coverage(document=document),
            baseline_failures=frozenset(cast("list[str]", document["baseline_failures"])),
        )
    except (OSError, ValueError, LookupError, TypeError):
        return None


def save_measurement(*, path: Path | None, key: str, measurement: Measurement) -> None:
    """Store a measurement under its key, unless coverage could not be measured."""
    if path is None or measurement.coverage is None:
        return
    names = sorted(
        {
            test
            for lines in measurement.coverage.values()
            for tests in lines.values()
            for test in tests
        }
    )
    number = {name: index for index, name in enumerate(names)}
    set_index: dict[frozenset[str], int] = {}
    files = {
        file: {
            str(line): set_index.setdefault(tests, len(set_index))
            for line, tests in sorted(lines.items())
        }
        for file, lines in sorted(measurement.coverage.items())
    }
    document = {
        "schema": MEASUREMENT_SCHEMA,
        "key": key,
        "baseline_failures": sorted(measurement.baseline_failures),
        "tests": names,
        "sets": [sorted(number[test] for test in tests) for tests in set_index],
        "coverage": files,
    }
    write_whole(path=path, text=json.dumps(document, sort_keys=True) + "\n")


def reuse_or_measure(
    *, path: Path | None, key: str, measure: Callable[[], Measurement]
) -> Measurement:
    """Return the stored measurement for this key, or measure now and store the result."""
    stored = load_measurement(path=path, key=key)
    if stored is not None:
        _ = sys.stderr.write(_REUSED)
        return stored
    measured = measure()
    save_measurement(path=path, key=key, measurement=measured)
    return measured
