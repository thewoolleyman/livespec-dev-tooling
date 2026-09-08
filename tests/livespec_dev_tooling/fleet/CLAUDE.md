# tests/livespec_dev_tooling/fleet/

Mirrors `livespec_dev_tooling/fleet/` one-to-one. Tests construct
`FleetContext` with a canned-response fake `GhRunner` (no network, no
real `gh`), so every assert/reconcile branch — pass, finding, skip,
unreadable — is exercised hermetically. Everything runs in-process,
including both CLI modules' entry points: `main()` is called directly
under a monkeypatched `sys.argv` / environment with `capsys`, and the
`if __name__ == "__main__":` line itself is excluded repo-wide by
`[tool.coverage.report].exclude_also` rather than covered by a spawn.
