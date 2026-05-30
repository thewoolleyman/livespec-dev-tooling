# livespec_dev_tooling/

The shared enforcement-suite library. Each shared check lives at
`checks/<slug>.py`, invocable as
`python -m livespec_dev_tooling.checks.<slug>`. Layout-dependent paths
are read from `config.py` (`load_config(repo_root=...)`) — the
`[tool.livespec_dev_tooling]` block in the consuming repo's
`pyproject.toml`, falling back to the livespec-core historical defaults
when the block is absent (per `SPECIFICATION/contracts.md` §"Consumer
configuration schema"). Third-party libraries are vendored under
`_vendor/` (excluded from every check's walk).
