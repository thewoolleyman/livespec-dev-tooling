"""Per-check modules invocable via `python -m livespec_dev_tooling.checks.<slug>`.

Empty at Phase G.2 of epic li-fgqgnk. Phase G.4 migrates each shared
check from livespec/dev-tooling/checks/<slug>.py to
livespec_dev_tooling/checks/<slug>.py, refactored for importability
and paired with a test at tests/livespec_dev_tooling/checks/test_<slug>.py.

Per livespec/SPECIFICATION/contracts.md §"Shared code sync —
livespec-dev-tooling", every check's argv contract and exit-code
semantics (0 = pass; non-zero = fail with structured stderr) are
part of the semver-stable surface and MUST NOT change without a
MAJOR version bump.
"""

__all__: list[str] = []
