"""livespec-dev-tooling — shared enforcement-suite library for livespec-governed projects.

The package surface is intentionally empty at Phase G.2 of epic
li-fgqgnk (tracked in livespec's own work-items store). Subsequent
phases migrate the 39 enforcement-suite scripts from
livespec/dev-tooling/checks/ into livespec_dev_tooling/checks/, where
each is invocable as `python -m livespec_dev_tooling.checks.<slug>`.

The semver-stable surface this package exports is the CLI surface of
those check modules (each check's argv contract and exit-code
semantics) plus the composite Actions and reusable workflows at
.github/. Internal module structure is implementation detail and MAY
change at any version increment per
livespec/SPECIFICATION/non-functional-requirements.md — file level
deliberately, since heading-level citations rot on rename and the
code-side rule forbids the form outright.
"""

__all__: list[str] = []
