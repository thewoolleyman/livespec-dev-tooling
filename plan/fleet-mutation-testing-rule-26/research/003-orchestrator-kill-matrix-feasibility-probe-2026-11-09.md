# Orchestrator Rule-26 kill-matrix feasibility probe, hp-xubuntu, 2026-11-09

This note records the bounded feasibility probe for
`livespec-dev-tooling-fqnbtd`. It is not the first-package kill-matrix report:
the probe covers only `effects/`, and its purpose was to establish whether the
then-shipped runner could complete the first-party package at all.

## Measurement

| field | value |
| --- | --- |
| target repository | `livespec-orchestrator-beads-fabro`, `master` |
| target subpackage | `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/effects/` |
| target size | 10 files; 1,725 lines |
| selected tests | the subpackage's own 21 tests, with `testpaths` restricted so mutmut's `mutants/` copy was not collected |
| host | hp-xubuntu (Linux) |
| engine | coverage-guided runner at livespec-dev-tooling `07fe1fc9`, with real mutmut 3.2.3 |
| generated mutants | 1,372 |
| killed mutants | 279 |
| surviving mutants | 1,093 (79.7%) |
| redundancy candidates | 9 of 21 tests (43%); the other 12 were the sole killer of at least one mutant |
| wall-clock | 15,571 s (4.3 h) |
| observed cost | 11.35 s per mutant |

The host load was approximately 10 to 33 during the run. The raw generated
report remains at
`hp-xubuntu:~/rule26-repro/orch-probe/reports/mutation-kill-matrix.json`.

## Extrapolation and decision

The first-party package is approximately 207,000 lines. Applying the probe's
mutant density gives approximately 165,000 mutants; at 11.35 seconds per
mutant, that is approximately 22 serial days. This is a lower bound: the probe
selected only `effects/` tests, whereas a package-wide run can select more
tests for a mutant.

The probe's 1,093 survivors are not a package-quality result. Other
orchestrator tests also exercise `effects/`, so their absence from the
restricted selection inflates survivors. The probe does establish that the
one-pytest-process-per-selected-test implementation could not practically
produce the full first-party report.

The required scaling work was filed as `livespec-dev-tooling-dkgwsm` and is
now merged as livespec-dev-tooling#3884 (`2f8cfb9e`). The coordinator removed
its former blocking edge to this item because the engine is available. The
remaining first-package run is host-captured work on poweredge-xubuntu: a k3s
Job with `nodeSelector kubernetes.io/hostname=poweredge-xubuntu`, CPU request
and limit 12, and `--workers 12`. If PSI60 remains above 30 for two reads after
launch, it must be reduced to eight workers and the measurements reported.

## Definition-of-Done status

The bounded-probe assertion is evidenced above. The full first-party
kill-matrix report remains outstanding: it must be generated from a non-zero
mutant set and list every survivor and every redundancy-candidate test. This
note deliberately does not substitute aggregate probe counts for that report.
