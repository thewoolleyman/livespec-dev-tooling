# `gha_runner` — per-host values for the inventory's `host_vars`

Measured from the live host `vps` (system hostname `vmi3006760`) on
2026-09-08 and carried here from `fabro-hosts` PR #16
`services/gha-runner/hosts/vps.env` (that shell installer was never merged:
the repository retired the installer convention first, and this role is where
the service landed).

**Why vps and not hp-xubuntu.** The job this runner serves,
`livespec-orchestrator-beads-fabro`'s `acceptance-live-golden-master.yml`, is
specified against the ORCHESTRATOR runtime — the pinned `fabro` binary, `bd`,
`dolt`, and the livespec 1Password wrapper — and vps is the host that carries
all four (`fabro` → `/home/ubuntu/.local/bin/fabro`, `bd` → `/usr/local/bin/bd`,
`dolt` → `/usr/local/bin/dolt`, `with-livespec-env.sh` →
`/usr/local/bin/with-livespec-env.sh`). An hp-xubuntu entry would be a
prediction about a host nobody has measured for this job. Enablement is
expressed by listing the role in that host's play and nothing else.

**The runner's identity is the operator account, deliberately.** The job is
specified against the operator's environment (the host fabro binary, the
docker daemon, the wrapper's sudoers entry). A dedicated user would buy no
isolation — it would still need the docker group, which is root-equivalent —
while forcing a copy of every host credential the job reads.

**Two credentials, two Apps.** The unit runs the runner under
`with-livespec-env.sh` so the livespec Environment's operator secrets are in
the job environment (the reason a GitHub-hosted runner cannot serve it).
Registration mints from `with-github-ci-runners-env.sh`, the
`github-ci-runners` Environment behind the `thewoolleyman-ci-runners` App —
the only App that holds `administration: write` on the repository (ARC
registers this repository's ephemeral runners through it). The livespec
Environment's App 3668528 holds contents/statuses/workflows and NOT
administration, so it cannot mint a registration token at all. Both wrappers
are role defaults because they are the same on every host that carries them.

```yaml
# vps
gha_runner_user: ubuntu
gha_runner_group: ubuntu
gha_runner_home: /home/ubuntu
# A DEDICATED tree — not the operator's home root and not the existing
# /home/ubuntu/gate-runner (livespec-dev-tooling's separate ephemeral gate
# tier), so the two runners' _work and _diag never collide.
gha_runner_root: /home/ubuntu/gha-runner
gha_runner_dir: /home/ubuntu/gha-runner/actions-runner
gha_runner_work: /home/ubuntu/gha-runner/_work
# What this runner serves. The labels are the ones the workflow selects on
# (`runs-on: [self-hosted, livespec-orchestrator]`); `self-hosted` is applied
# automatically by the runner and is listed so the file states the whole
# selector a reader has to match against the workflow.
gha_runner_repo: thewoolleyman/livespec-orchestrator-beads-fabro
gha_runner_name: vps-livespec-orchestrator
gha_runner_labels: self-hosted,livespec-orchestrator
# PATH for the runner process and therefore every job step. The job wrapper
# scrubs the environment (`env -i`) and hard-codes PATH to the system
# secure_path, which does NOT carry this host's `fabro` — so the launcher
# re-exports THIS value after the wrapper has run. Measured 2026-09-08.
gha_runner_job_path: /home/ubuntu/.local/share/mise/shims:/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

`GHA_RUNNER_SYSTEM_HOSTNAME` and `GHA_RUNNER_CANONICAL_HOST` from the shell
values file are deliberately **not** host vars: both existed only for the
installer's hostname guard, which inventory targeting replaces.
