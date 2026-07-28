# livespec_dev_tooling/checks/

One module per shared check, each invocable as
`python -m livespec_dev_tooling.checks.<slug>` and exiting non-zero on a
violation. A check reads its layout-dependent source trees from
`livespec_dev_tooling.config.load_config(repo_root=Path.cwd())` and walks
them via `iter_py_files` (which skips `_vendor`/`__pycache__`). A check
whose governing role key the consumer declares ABSENT logs a structured
no-op and exits 0. For a key in `UNION_ROLE_KEYS` that declaration is one
of the four blessed inline tables carrying a non-empty payload
(`not_applicable`, `superseded_by`, `unarmed_until`,
`convention_not_adopted`) — a bare `[]` / `""` is the retired ambiguous
spelling and is now a hard `ConfigParseError` at load
(SPECIFICATION v033). For every other required key a bare `[]` remains
legitimate, because those keys scope an exemption or a severity rather
than a scan universe, so emptiness makes their consuming check stricter
rather than blinder (v033 §"Clean role keys retain `[]`"). An UNDECLARED
key is a hard ERROR naming it (v0.54.12): absence is no longer a spelling
of "not applicable", and a declared non-empty key resolving to
no `.py` at all is likewise an error, since an armed check inspecting
nothing is a misconfiguration rather than a pass. Diagnostics flow through the vendored
`structlog` (JSON to stderr) — `print`/`sys.*.write` are banned here.
