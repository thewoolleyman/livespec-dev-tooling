"""A coverage namespace's TMPDIR is owner-only whatever the umask of the process that made it.

Work-item livespec-dev-tooling-o6u7jm. `build_namespace_dirs` makes each namespace's `tmp/`
directory, the per-target TMPDIR that pytest's `tmp_path` derives from. It inherited the
process umask, so a pushing host running at umask 0002 gave it group write, and every test
that needs a path whose ancestors are all unwritable by group and other (the expedited-incident
`protected_path` rule) failed under the gate while passing in a plain checkout.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import livespec_dev_tooling._dispatcher_coverage_namespaces as namespaces

__all__: list[str] = []


def test_the_namespace_tmpdir_is_owner_only_under_a_group_writable_umask(tmp_path: Path) -> None:
    previous = os.umask(0o002)
    try:
        dirs = namespaces.build_namespace_dirs(
            targets=["check-check-coverage-incremental"],
            skip_set=frozenset(),
            root=tmp_path,
        )
    finally:
        _ = os.umask(previous)
    modes = [stat.S_IMODE((ns_dir / "tmp").stat().st_mode) for ns_dir in dirs.values()]
    assert dirs
    assert modes == [0o700] * len(dirs)
