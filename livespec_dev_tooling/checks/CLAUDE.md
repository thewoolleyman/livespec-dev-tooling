# livespec_dev_tooling/checks/

One module per shared check, each invocable as
`python -m livespec_dev_tooling.checks.<slug>` and exiting non-zero on a
violation. A check reads its layout-dependent source trees from
`livespec_dev_tooling.config.load_config(repo_root=Path.cwd())` and walks
them via `iter_py_files` (which skips `_vendor`/`__pycache__`); a check
whose governing role key is absent for the consumer logs a structured
`info` no-op and exits 0. Diagnostics flow through the vendored
`structlog` (JSON to stderr) — `print`/`sys.*.write` are banned here.
