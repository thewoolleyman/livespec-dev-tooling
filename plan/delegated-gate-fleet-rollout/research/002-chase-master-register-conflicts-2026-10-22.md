# Chase-master refreshes and the generated debt register (2026-10-22)

Recorded by `claude:delegated-gate-fleet-rollout` while resuming epic
`livespec-dev-tooling-mvalxq`.

## What happened

Three implementation children of this plan's neighbourhood ended a green run
blocked as `livespec-base-advanced-after-arming` on 2026-10-22, and each
chase-master refresh had to resolve a conflict on
`tests/heading-coverage-debt.json`:

- `livespec-dev-tooling-ouk27x`.
- `livespec-dev-tooling-ltkxq2`. Re-run `01M5GWSFZPN6` hand-merged the
  register, lost master's rows, and ended needs_human. It was rebased by hand
  under coordinator ruling R555, with the register regenerated. That was
  PR #2745, merged as `0faa601e` and released in v1.123.0.
- `livespec-dev-tooling-7kvh2d`. PR #2751 was DIRTY: both it and master had
  edited `tests/heading-coverage-debt.json` and `tests/heading-coverage.json`.
  Its re-proof is `01M5H2ZY5PRM`.

## The cause and where its fix lives

`refresh_repair` resolves a conflicted generated register by merging its text.
It should run the repository's declared generator over the merged tree. The
orchestrator defect is `bd-ib-ze7xxj`, raised to P1 under coordinator ruling
R564.

## Standing handling until the fix ships

- If a chase-master run ends DEFECTIVE on the register, do not re-run it
  (R258). Rebase by hand, regenerate the register with
  `just generate-heading-coverage-debt-register`, and push with
  `--force-with-lease` to the PR's own branch through the full pre-push gate.
- Launch register-adoption items (`livespec-runtime-4tovih`,
  `livespec-console-beads-fabro-2zurwc`) only on repositories whose masters are
  quiet, and keep each merge window short (R564).
