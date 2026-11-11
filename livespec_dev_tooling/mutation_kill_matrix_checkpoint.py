"""Checkpoint the Rule-26 kill matrix's result cache while execution runs.

A full target selects tens of millions of test runs, which can outlast the
Job that runs them.  The cache used to be written only once execution ended,
so a run ended by its deadline kept nothing.  A `Checkpoint` receives each
finished mutant from the worker pool and, at most every `every_seconds`,
saves every outcome so far, reused and finished, to the cache.  A later run
then reuses those outcomes through the ordinary content-keyed cache (see
`mutation_kill_matrix_cache`).  Each save also logs how many of the pending
mutants have finished, so a long execution is observable.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from livespec_dev_tooling.mutation_kill_matrix_cache import CachedOutcome, save_cache

__all__: list[str] = [
    "Checkpoint",
]


@dataclass(kw_only=True)
class Checkpoint:
    """Collect finished outcomes by cache key and save them on an interval.

    `keys` maps each pending mutant to its cache key; `seeded` holds the
    reused outcomes, already keyed, so every save is the whole cache so far.
    """

    path: Path | None
    keys: dict[str, str]
    seeded: dict[str, CachedOutcome]
    total: int
    every_seconds: float = 300.0
    clock: Callable[[], float] = time.monotonic
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    _entries: dict[str, CachedOutcome] = field(init=False)
    _done: int = field(init=False, default=0)
    _last: float = field(init=False)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self._entries = dict(self.seeded)
        self._last = self.clock()

    def record(self, *, identifier: str, outcome: CachedOutcome) -> None:
        """Keep one finished mutant's outcome, saving everything when the interval has passed."""
        with self._lock:
            self._entries[self.keys[identifier]] = outcome
            self._done += 1
            now = self.clock()
            if now - self._last < self.every_seconds:
                return
            self._last = now
            if self.path is not None:
                save_cache(path=self.path, entries=self._entries)
            _ = self.stream.write(
                f"mutation-kill-matrix: executed {self._done}/{self.total} mutants\n"
            )
