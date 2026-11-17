# Reproduce A Failure In Its Own Container

Use this when a factory run node, a CI job, a gate Job, a flaky test or a probe has failed and its cause is
not already known from evidence. Use it BEFORE any retry, relaunch, re-dispatch or "wait for the next factory
run". Every one of those runs in a published container image, so the failing command can be run again in
the same image, on a route that "Route by failure class" below names for each class. Some classes have no
lawful same-image route from a seat yet, and that section says what to do instead.

The maintainer, 2026-11-17 ~03:5xZ, to throughput-plans-coordinator: "So are you thrashing and not using this
clear tool that you have available, where everything is containerized and you can easily reproduce problems
locally? Are you just waiting on the factory every fucking time something breaks? And retrying it over and over
rather than specifically and explicitly debugging it locally ?" And to legacy-coordinator-agent: "… Record this
as ongoing permanent guidance for coordinators to tell seats how to debug things . And also some other prominent
separate AI instruction that says how to reproduce uncertain bugs . Everything's containerized for a fucking
reason. Leverage it" [6tgd2z 2026-11-17T03:5xZ, rule REPRODUCE-LOCALLY-FIRST].

## The rules

1. **Reproduce first, in the identical image.** Use the same image tag and the same tree, and run the same
   command.
2. **No retry, relaunch or re-dispatch before the repro.** A bounded flake retry of work already in progress
   (`.ai/coordinator-duties.md` §2) may run in parallel. It never takes the repro's place.
3. **A repro outside the failing environment does not count.** That includes a plain checkout, the host shell,
   another image tag or another CPU architecture. If it passes while the real run fails, it proved nothing
   about the failure. It only shows that the difference is in the environment, so chase that next.
4. **Waiting on a factory run is never a debugging step.**
5. **Record the measured cause on the work item**: the image, the tree, the command, the exit status and the
   line that names the cause.

**The floor: a repeat in a row means local debugging, always.** The maintainer, 2026-11-17 ~04:0xZ: "Anytime
anything fails in the factory or CI more than twice in a row for the same reason, you should debug it locally,
always" [6tgd2z 2026-11-17T04:0xZ]. This is mechanical and needs no judgment. When the same failure signature
recurs in a row in the factory or CI, the failure MUST be debugged locally in the identical container, and
nothing is retried or relaunched until the cause is measured and fixed. No label (flake, transient, infra)
exempts a repeating signature. Rule STOP-AT-SECOND (`.ai/coordinator-duties.md` §10) stops new launches. This
floor says what the seat does instead: it debugs locally, on the route the table below gives for the failure's
class.

What skipping this cost on 2026-11-17: driver-claude's `commit_green` failure was never reproduced and failed
twice. git-jsonl was retried three times on a probe token error. A slow coverage job was re-run instead of
measured.

## Route by failure class

| Failure class | Lawful repro route |
|---|---|
| Gate image (a delegated pre-commit or pre-push gate Job) | `mise exec -- just gate-repro <repo_root> …` (`justfile:457`, `ci-runner/k3s/phase2/gates/gate-repro.sh`). It runs the gate client and a rendered Job on queue `gates-repro-lq`. It runs only on gamingpc-xubuntu and only with the GATE image. |
| ARC runner image (a CI job) or factory SANDBOX image (a factory node) | No lawful same-image route from a seat exists today; see below. Measure the real run (the next row), or run the failing node's command inside the factory's own sandbox through a normal factory run of a diagnostic item. |
| Node-specific performance (a job that is slow on one node only) | Measure the real run on that node: `sar` history for the job's disk, Honeycomb per-pod `k8s.pod.cpu.usage`, and the kubelet journal (`.ai/deleted-gate-pod-diagnosis.md`, `.ai/ci-node-capacity-reads.md`). A new pod elsewhere does not reproduce it. |

**For ARC runner image and factory sandbox image failures, a seat has NO lawful same-image route today.**
`fleet_host_guard` refuses a hand probe pod (`ssh <node> sudo k3s kubectl apply -f -`). On 2026-11-17 ~05:0xZ it
also refused `ssh vmi3006760 docker pull <runner image>` as a by-hand fleet change. The committed repro lane is
being built as livespec-dev-tooling-cwrg3v (gate-job-resources). Until it lands, reproduce such a failure in one of
two ways. Either measure the real run, or put the failing node's command into a diagnostic work item and let a
normal factory run execute it inside the factory's own sandbox. Dispatch that run through petri like any other
(`.ai/fabro-dispatch-diagnosis.md`). That run is the repro, not a retry of the failed item. **Never route around a
guard refusal, and never respell a refused command.** Report the refusal as a missing lane.

## Find the exact image and tree

**Factory run (petri or candidate).** The image comes from the factory's catalog, not from the workflow's pin,
so read it from the run itself. Use the client named by the factory's `bin` in the dispatching repository's
`.livespec.jsonc`. Petri is `:32276` and candidate is `:32278`. Use `--server` every time, because a bare call
asks the wrong server (`.ai/fabro-dispatch-diagnosis.md`).

```bash
F=$HOME/.local/state/fabro-currency/carrier-petri-v0.393-bbe693847/fabro
S=https://gmktec-xubuntu.perch-rudd.ts.net:32276
"$F" inspect --json <run-id> --server "$S" | jq -r '.[0].sandbox.instance.image,
  .[0].run_spec.labels["livespec.dispatch.id"], .[0].run_spec.labels["livespec.repository"]'
"$F" dump <run-id> -o <empty-dir> --server "$S"
```

Measured on run `01M7KR00K1FP` on 2026-11-17: the run used `python-agent-v1.188.1`, which is petri's catalog
image (`ansible/inventory/host_vars/gmktec-xubuntu.yml`, `sandbox_providers.kubernetes.process_spec.image`). The
orchestrator's `implement-work-item/workflow.toml` pins `v1.208.0`, so reading the pin gives the wrong image. The
dump holds the graph as the engine ran it (`graph.fabro`) and one directory per node visit,
`stages/<NNN>-<node>@<visit>/`. Each holds `script_invocation.json` (the exact command), `status.json` (the
`failure_reason`) and `output.log`. `checkpoints/*.json` give each checkpoint's `git_commit_sha`.

The tree of a failed run is its preserve ref in the target repository,
`git ls-remote origin refs/heads/needs-human/<dispatch-id>`. For a run that published a PR, use the PR head. If
there is no preserve ref, follow "Preserve before any cancel" (`.ai/coordinator-duties.md` §10) first. Runs on
the `homelab-worker-arm64` factory use the `-arm64` image.

**CI job.** The image is the job's `container: image:` in the workflow at the run's head commit. The ARC job log
does not print it (checked on 2026-11-17).

```bash
sha=$(gh run view <run-id> -R livespec-ai/<repo> --json headSha -q .headSha)
gh api -H 'Accept: application/vnd.github.raw' \
  "repos/livespec-ai/<repo>/contents/.github/workflows/ci.yml?ref=${sha}" | grep -n 'image:'
```

**Gate Job.** A delegated gate pod runs the gated repository's own CI image. `render-gate-job.sh` reads it from
that repository's workflow into `gate-job-template.yaml`'s `@@IMAGE@@` (`ci-runner/k3s/phase2/gates/`), so look
it up the same way, at the gated tree.

## Run a gate repro on the cluster

Run `mise exec -- just gate-repro <repo-root>` (`ci-runner/k3s/phase2/gates/gate-repro.sh`). It submits ONE gate
Job for the committed tree through the normal gate client, onto queue `gates-repro-lq` in namespace `gates`
(gamingpc-xubuntu), and it keeps the Job's logs under `tmp/gate-repro/`. Never hand-create a pod or Job
(`kubectl run`, `create` or `apply`, directly or over `ssh`): `fleet_host_guard` refuses it, and the gates
credential cannot delete pods (`gates-rbac.yaml`), so a `kubectl run --rm` pod would leak. Namespace `factory`
belongs to the sandbox driver. Never create anything there.

**Stay read-only.** A repro never pushes to a working branch, never writes config, secrets or the ledger, and
never prints a secret value. A retained factory sandbox is evidence only. Never repair it in place.

## Reproducing a factory node

1. Dump the run and open the failing stage's `status.json` and `output.log`. These often name the cause outright.
   Run `01M7KR00K1FP` `commit_green@3` read "current run's own Red commit was not found beneath checkpoint
   commits".
2. The node's exact command is in that stage's `script_invocation.json`. The `stages/*run_prepare_*` directories
   are the setup that ran before it. `checkpoints/*.json` give the tree at each step.
3. A prepare step writes the helpers a node calls under `$HOME/.claude/plugins`, using the dispatch payload. Their
   source is in the orchestrator. For example, `livespec-commit-green.sh` comes from
   `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_commit_green_program.sh`, at the
   build the dispatching project has installed (`.ai/stale-plugin-build-path.md`). Read it next to the stage's
   output before forming a theory.
4. A `commit_green` or gate refusal comes from the repository's own hooks. The refused target
   (`mise exec -- just <target>`) or the run's `sandbox_check_suite` input
   (`mise exec -- just install-worktree-pack check`) on the preserved tree is the command to reproduce. Run it
   through `just gate-repro` if it is a gate, or through a diagnostic item's factory run if it needs the sandbox
   image.

If the repro passes while the run failed, record that and chase the difference (resources, node, network,
credentials, plugin build). Never relaunch to "see if it happens again".
