# tests/livespec_dev_tooling/fleet/

Mirrors `livespec_dev_tooling/fleet/` one-to-one. Tests construct
`FleetContext` with a canned-response fake `GhRunner` (no network, no
real `gh`), so every assert/reconcile branch — pass, finding, skip,
unreadable — is exercised hermetically. The two CLI modules each get
one `python -m` subprocess invocation to cover the `__main__` guard;
everything else runs in-process.
