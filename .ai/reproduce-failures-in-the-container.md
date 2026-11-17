# Reproduce A Failure In Its Own Container

Use this when a factory run node, a CI job, a gate Job, a flaky test or a probe has failed and its cause is
not already known from evidence. Use it BEFORE any retry, relaunch, re-dispatch or "wait for the next factory
run". Every one of those runs in a published container image, so the failing command can be run again, by
hand, in the same image, usually in seconds or minutes. A factory run takes hours, so waiting for one costs
far more than a repro.

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
floor says what the seat does instead: it debugs locally.

What skipping this cost on 2026-11-17: driver-claude's `commit_green` failure was never reproduced and failed
twice. git-jsonl was retried three times on a probe token error. A slow coverage job was re-run instead of
measured.

## Step 1: find the exact image and tree

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
the `homelab-worker-arm64` factory use the `-arm64` image. The dev host (vmi3006760) is x86_64 and has no arm64
emulator registered, so reproduce those on an arm64 host.

**CI job.** The image is the job's `container: image:` in the workflow at the run's head commit. The ARC job log
does not print it (checked on 2026-11-17).

```bash
sha=$(gh run view <run-id> -R livespec-ai/<repo> --json headSha -q .headSha)
gh api -H 'Accept: application/vnd.github.raw' \
  "repos/livespec-ai/<repo>/contents/.github/workflows/ci.yml?ref=${sha}" | grep -n 'image:'
```

Copy the job's `env:` block too. In `ci.yml` that block sets `MISE_DATA_DIR=/root/.local/share/mise` and
`MISE_NOT_FOUND_AUTO_INSTALL=0`.

**Gate Job.** A delegated gate pod runs the gated repository's own CI image. `render-gate-job.sh` reads it from
that repository's workflow into `gate-job-template.yaml`'s `@@IMAGE@@` (`ci-runner/k3s/phase2/gates/`), so look
it up the same way, at the gated tree.

## Step 2: run the failing command in that image

**On the dev host with docker** (vmi3006760 has docker 28 and podman). Put this in a scratchpad script and run
it with `bash <file>`. The tree is mounted read-only and cloned inside the container. The push URL is disabled,
and no secret is passed in. Checked on 2026-11-17: `check-format` on a preserve ref in `python-v1.183.1` took
17 s from start to finish.

```bash
set -euo pipefail
repo=livespec-dev-tooling
src=refs/heads/needs-human/<dispatch-id>   # or a PR branch ref, or a full commit sha
img=ghcr.io/livespec-ai/livespec-fabro-sandbox:python-agent-v1.188.1
cmd='mise exec -- just check-format'       # the exact failing command
dir=$(mktemp -d)
gh repo clone "livespec-ai/${repo}" "${dir}/src" -- -q --reference-if-able "$HOME/workspace/${repo}" --dissociate
git -C "${dir}/src" fetch -q origin "+${src}:refs/heads/repro"
git -C "${dir}/src" remote set-url --push origin DISABLED
docker run --rm --cpus 6 --memory 8g -v "${dir}/src":/src:ro \
  -e MISE_DATA_DIR=/root/.local/share/mise -e MISE_NOT_FOUND_AUTO_INSTALL=0 \
  "${img}" bash -lc "git config --global --add safe.directory '*' &&
    git clone -q -b repro /src /workspace && cd /workspace && ${cmd}"
```

- `--cpus 6 --memory 8g` matches the `factory-python` environment (cpu 6, memory 8GB). Change it to match the
  failing job's limits.
- Inside the container, `origin/master` is the host clone's `master`. Diff-based checks therefore see a real
  base.
- Do not use `--filter=blob:none`. A partial clone cannot be cloned again from `/src`, and checkout fails with
  `unable to read sha1 file`.
- Use braces in `"+${src}:refs/…"`. In zsh, `$src:r` is a history modifier and mangles the refspec
  (`.ai/livespec-operation-gotchas.md`).

**On the cluster**, when the failure depends on the node (the cache tier, CPU contention, the pod network), run
`mise exec -- just gate-repro <repo-root>` (`ci-runner/k3s/phase2/gates/gate-repro.sh`). It submits ONE gate Job
for the committed tree through the normal gate client, onto queue `gates-repro-lq` in namespace `gates`, and it
keeps the Job's logs under `tmp/gate-repro/`. Never hand-create a pod or Job (`kubectl run`, `create` or
`apply`): `fleet_host_guard` refuses it, and the gates credential cannot delete pods (`gates-rbac.yaml`), so a
`kubectl run --rm` pod would leak. Namespace `factory` belongs to the sandbox driver. Never create anything there.

**Stay read-only.** The repro never pushes, never writes config, secrets or the ledger, never runs a credential
wrapper inside the container, and never prints a secret value. A retained factory sandbox is evidence only.
Reproduce in a fresh container, never by repairing the retained one.

## Reproducing a factory node

1. Dump the run and open the failing stage's `status.json` and `output.log`. These often name the cause outright.
   Run `01M7KR00K1FP` `commit_green@3` read "current run's own Red commit was not found beneath checkpoint
   commits".
2. The node's command is in that stage's `script_invocation.json`. The `stages/*run_prepare_*` directories are
   the setup that ran before it. Replay the setup steps that use no credential, such as `mise install`,
   `uv run lefthook install`, `git fetch origin master`, `mise exec -- just install-worktree-pack` and
   `uv sync --all-groups`. Skip any step that writes a token, `auth.json` or a credential helper.
3. A prepare step writes the helpers a node calls under `$HOME/.claude/plugins`, using the dispatch payload. Their
   source is in the orchestrator. For example, `livespec-commit-green.sh` comes from
   `.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_commit_green_program.sh`. Use the
   build the dispatching project has installed (`.ai/stale-plugin-build-path.md`). Mount it read-only and run it
   with the arguments from `script_invocation.json`.
4. A `commit_green` or gate refusal comes from the repository's own hooks. Run the refused target
   (`mise exec -- just <target>`) or the run's `sandbox_check_suite` input
   (`mise exec -- just install-worktree-pack check`) on the preserved tree.

If the repro passes while the run failed, record that and chase the difference (resources, node, network,
credentials, plugin build). Never relaunch to "see if it happens again".
