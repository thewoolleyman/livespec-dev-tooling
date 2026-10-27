# Reading a red post-merge janitor

A `reconcile-merged` or dispatch drive that ends `failed at janitor-post-merge`
has already kept everything you need to name the failure. Read what it kept
before you reproduce anything. A reproduction of this repository's suite costs
about 35 minutes, and on a loaded host it can PASS where the janitor failed.

## Where the output is

The journal row, the gate's `output.log` and the dispatcher's one-line detail
show only a JSON timing tail. That is because the `just check` aggregate writes
each target's captured output to STDOUT and only its structlog timing events to
stderr. The complete streams are kept elsewhere, as orchestrator Scenario 145
requires:

```text
<repo>/tmp/janitor-failed-output/<dispatch-id>-janitor-post-merge-<id>.json
```

The JSON keys are `stdout`, `stderr` and `exit_code`. Search `stdout` for the
pytest `FAILURES` block. Search for `.json` under that directory. A search for
`*.log` files finds nothing, and a 2026-10-27 session concluded from that empty
result that the janitor discarded its output. It does not, and the claim had to
be retracted to the coordinator.

## The two-second first look

The janitor's checkout is kept for diagnosis (the path is in the red detail).
Two files in it answer the first question:

- `.pytest_cache/v/cache/lastfailed` names the failing test ids.
- `.livespec-coverage-reuse-token` is written only after pytest exits 0. If
  `check-per-file-coverage` is the red target and this file is ABSENT, pytest
  itself failed, not the per-file threshold. Running
  `uv run python -m livespec_dev_tooling.checks.per_file_coverage` in that
  checkout then passes on the kept `.coverage`.

Check whether a file exists with `test -e`, never `ls`: `ls` is aliased to lsd
here and reports FALSE ABSENCES (see `.ai/livespec-operation-gotchas.md`).

## What the 2026-10-27 reds were

Four janitor reds on livespec-dev-tooling-rval5v named four different tests,
each passing on an idle shell:

1. `render-gate-job-exit-tests.sh` case R: `upstream | grep -q` under
   `pipefail` (SIGPIPE, exit 141 read as no match). Fixed in PR #2907.
2. `test_mint_private_sibling_token.py`: a fake `openssl` that exited without
   draining stdin, so the minter exited 141. Fixed in PR #2908.
3. `test_factory_credential_refresh.py:266`: `assert 1 == 0`. Unresolved. The
   test does not print the script's stderr, so which `exit 1` fired is not
   recorded.

The SIGPIPE shape is swept fleet-wide by livespec-dev-tooling-mfk3h4. The
host's spawn churn that makes these races fire is livespec-dev-tooling-kfj72q.
