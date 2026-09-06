# livespec_dev_tooling/

The shared enforcement-suite library. Each shared check lives at
`checks/<slug>.py`, invocable as
`python -m livespec_dev_tooling.checks.<slug>`. Layout-dependent paths
are read from `config.py` (`load_config(repo_root=...)`) — the
`[tool.livespec_dev_tooling]` block in the consuming repo's
`pyproject.toml`, falling back to a bare flat baseline with NO declared
keys when the block is absent, which is not a working configuration: every
required role key is then undeclared, so each role-gated check hard-errors
naming the key rather than silently scanning nothing (per
`SPECIFICATION/contracts.md` §"Consumer configuration schema").
Third-party libraries are vendored under
`_vendor/` (excluded from every check's walk).

Everything here SHIPS, so every message it emits is read in a consumer
repo. When a message cites a document, name the repo that owns it — a bare
repo-relative path resolves only where the file lives, and dropping the
citation where it does not resolve strands the reader instead. See
`docs/shipped-message-doc-citations.md` for the rule, the 2026-09-06 audit
of all 36 citation sites, and why no mechanical check guards it.
