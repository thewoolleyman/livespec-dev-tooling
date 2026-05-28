# tests/

Mirrors `livespec_dev_tooling/` one-to-one (per the
`tests_mirror_pairing` discipline).

Conventions:

- pytest is the test framework (`uv run pytest tests/` or
  `just check-per-file-coverage` for the per-file 100% gate).
- Every directory under `tests/` (except `fixtures/` subtrees)
  carries a `CLAUDE.md` per `check-claude-md-coverage`.
- `tests/heading-coverage.json` is the heading-coverage registry
  consumed by `check-heading-coverage` (canonical aggregate slug
  per epic li-univck Phase 1.4 self-host wiring).
