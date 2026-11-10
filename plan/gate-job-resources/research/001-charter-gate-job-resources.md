## The maintainer's statement of what done means

lets parallelize it, make this a plan ... and make it a priority next to the suite double-run fix. I am bringing more capacity online. ANd I also want to know why HP and gmktec are sitting mostly idle (and a lot idle on poweredge right now), when we are claiming there's no cluster capacity

## Definition of Done assertions derived from that statement

- A repository that declares gate_cpu, gate_memory and gate_parallelism under [tool.livespec_dev_tooling] gets a gates Job that requests exactly those values, and a repository that declares none still gets today's 5 cpu, 6Gi and 4 test workers.
- A single-file Red/Green replay gates Job requests less cpu and memory by default than a full-suite gates Job.
- The gates Kueue flavor quotas admit at least as many concurrent full-suite gates as today's seven (gmktec-xubuntu 3, poweredge-xubuntu 2, hp-xubuntu 2) after the request changes.
- The wall time of the orchestrator's check-per-file-coverage at 8 and at 12 test workers, each taken through the normal gate client, is recorded beside the 4-worker baseline of 2,174 s from gmktec-xubuntu pod zvqpl before any default moves.
- The orchestrator's committed gate parallelism equals the best measured value, and every fleet repository's gate cpu, memory and parallelism value is named.
- Every gates and factory cap that holds gmktec-xubuntu, hp-xubuntu or poweredge-xubuntu capacity idle while work queues is named with its measured value and is either raised or carried by a routed item.

# gate-job-resources — charter

Created 2026-11-11 ~00:3xZ by the gate-job-resources seat, from the
legacy-coordinator-agent seat brief (coordinator session 4e17d8e9). Priority
3b: one slot shared with 3a, implement-test-performance's suite double-run
fix; the two run in parallel. The maintainer's direction is recorded on epic
livespec-dev-tooling-6tgd2z (priorities record).

The Definition of Done above was derived by the coordinator from the
maintainer's words and the measured finding below, and adopted unchanged by
this seat. It was not confirmed with the maintainer in an attended picker
(coordinator-duties §6: seats never block on a picker).

## The problem, as measured

Every fleet gates Job (the delegated commit/push gate that
`gate_remote_delegate.py` renders through `render-gate-job.sh` and submits to
the Kueue `gates-cq`) requests the same shape, whatever repository or gate it
runs:

- `cpu: 5` request, no cpu limit; `memory: 6Gi` request and limit;
  `LIVESPEC_TEST_PARALLELISM=4` (`ci-runner/k3s/phase2/gates/render-gate-job.sh:98`,
  `gate-job-template.yaml:715`, `:756-765`).
- The renderer already accepts `--cpu`, `--memory` and `--parallelism`, but
  its single caller, `livespec_dev_tooling/gate_remote_delegate.py:323-341`,
  never passes them. So a one-file Red/Green replay Job takes the same
  5 cpu / 6Gi as a full-suite coverage gate.
- Kueue `gates-cq` flavor quotas (`ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml`):
  `gates-flavor` (gmktec-xubuntu) 15 cpu / 24Gi, `gates-poweredge-flavor`
  (poweredge-xubuntu) 10 cpu / 16Gi, `gates-hp-flavor` (hp-xubuntu)
  10 cpu / 16Gi. At 5 cpu per Job that is 3 + 2 + 2 = 7 concurrent gates
  fleet-wide.
- Node sizes (`ci-runner/k3s/phase2/factory/DERIVATION.md:32-34`):
  poweredge-xubuntu 72 CPU, gmktec-xubuntu 32 threads, hp-xubuntu 16.
- gmktec-xubuntu `mpstat` read 80.23 % idle at 2026-11-10 23:13Z (load 9-12),
  while gates queued (implement-test-performance's measurement).

Baseline: orchestrator `check-per-file-coverage` in gmktec gate pod `zvqpl`:
pytest 2,174 s over 14,969 tests at 4 workers; target wall 2,222 s.

Fleet coverage workers inside the Job today: 4 for livespec,
livespec-dev-tooling, livespec-orchestrator-beads-fabro,
livespec-orchestrator-git-jsonl, livespec-overseer and livespec-runtime;
serial for livespec-console-beads-fabro and the three drivers (claude, codex,
pi).

Nothing at 8 or 12 workers is measured yet. A hand `kubectl create` of a
gates Job is refused by `fleet_host_guard` (a server dry-run passes), so the
measurement goes through the normal gate client once a repository can declare
its resources — never around the guard.

## Approach

1. Spec first: the proposal `a-consumer-declares-its-gate-job-resources`
   (being filed by implement-test-performance's background session on branch
   `spec/gate-job-resources`; ownership moves to this plan at its PR). It
   carries the declaration surface, the quota floor and the smaller replay
   default. This seat revises it, then files implementation children.
2. Implementation: `[tool.livespec_dev_tooling]` `gate_cpu`, `gate_memory`,
   `gate_parallelism`, read by `gate_remote_request` / the delegate and passed
   to `render-gate-job.sh`; defaults unchanged. Single-file Red/Green replay
   Jobs take a smaller default.
3. Quotas: the gates flavor quotas rise with the request so concurrency does
   not fall (read `.ai/ci-node-capacity-reads.md` first; a cap is
   throughput-derived, and every value cites a job read).
4. Measurement through the normal gate client: orchestrator coverage at 8 and
   12 workers, before any default moves.
5. Default moves for the orchestrator to the measured best; fleet values named
   per repository.
6. Capacity: every gates and factory cap that strands idle capacity on
   gmktec-xubuntu, hp-xubuntu and poweredge-xubuntu is named with its measured
   value (Kueue flavor quotas, the factory fleet-cap, ARC maxRunners,
   scheduler requests). The coordinator's capacity helper result is routed
   into this plan as DoD-carrying children or routed items.

## Scope boundary

implement-test-performance keeps the suite double-run proposal and its
children. This plan owns the gate-resources proposal and every child it
spawns. FLEET SCOPE: every repository's gates Job.
