# Factory sandbox backend runbook: Kubernetes pods, the Docker fallback, and rescue

This runbook is for the `petri` factory, the fleet Fabro instance on
`gmktec-xubuntu` (port 32276, unit `fabro-server`). It covers four things:

1. The cutover that put this factory's sandboxes on Kubernetes.
2. How to switch the factory to Docker and back. Both directions were tested
   end to end with real dispatches.
3. How to rescue the work of a stranded run whose sandbox is a pod.
4. What to do when the cluster becomes unavailable while runs are in flight.

It belongs to plan `kubernetes-sandbox-backend` (epic `bd-ib-nmuyjc`, work-item
`bd-ib-nmuyjc.2`, in the livespec-orchestrator-beads-fabro tenant). The play it
drives is `ansible/fabro-hosts.yml`, which sits next to this file. Every host
change below is a git change followed by the committed apply. Nothing is changed
on a host by hand.

## How the backend is selected

A dispatch from any fleet repository names a catalog **environment id** through
its committed `dispatcher.factories.petri.environment`. For the python
toolchain that id is `factory-python`. The environment's `provider` decides
where the sandbox runs. It is declared in
`ansible/inventory/host_vars/gmktec-xubuntu.yml` under
`fabro_server_instances.fabro-server.environments`:

| `provider` | Where the sandbox runs | What it carries |
| --- | --- | --- |
| `kubernetes` | Pod `petri-<run-id lower-case>-l<lease>` in namespace `factory`, launched by `/usr/local/bin/sandbox-driver-kubernetes` with `/etc/ci-runner/factory.kubeconfig` | No `image`. The image comes from `sandbox_providers.kubernetes.process_spec`. |
| `docker` | Container `petri-<RUN-ID>-l<lease>` on gmktec's own Docker engine | `image: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-<tag>` |

SPECIFICATION "Factory sandbox environment naming" says placement is never in
the id. So switching backends edits `provider` (and `image`) on the same id. No
fleet repository's committed configuration changes. The catalog is
server-managed, so the role converges the edit with a `PUT
/api/v1/environments/factory-python` and no server restart.

A pod's workspace is a `hostPath` volume at
`/srv/factory-workspaces/<sandbox-name>` on the node that ran it. That
directory outlives the pod. Today every factory pod runs on
`poweredge-xubuntu`, which is also the k3s control plane. Spreading pods across
nodes is work-item `bd-ib-kogktm`.

## 1. The cutover to Kubernetes (record)

- 2026-10-24: the coordinator ruled the cutover on
  `livespec-dev-tooling-dfixhe`, after the third canary run `01M5NQK36G7K`
  passed its pod bar on `sandbox-driver-kubernetes` v0.4.1.
- The catalog now declares `livespec-ci`, `livespec-ci-k8s` and `factory-python`
  on `provider: kubernetes`. `factory-python` was named in rename step 1
  (`livespec-dev-tooling-s6go5s`).
- In the orchestrator tenant, PR #3571 (`6dd2a3354`) pointed the petri factory
  entry at the Kubernetes environment, and PR #3576 (`88ef92242`) renamed it to
  `factory-python`.
- Evidence (on `bd-ib-nmuyjc.1`, closed 2026-10-31):
  - Canary run `01M5P2MHPH2Z` ran in a pod and merged livespec-dev-tooling #2812.
  - Pod `petri-01m69000btycsps4ty8e3tnwcq-l0` had requests equal to limits:
    4 CPU and 7630Mi, QoS Guaranteed.
  - Re-dispatch `01M64EV6AVYW` on provider kubernetes merged #3971.

## 2. Switching the factory to Docker and back

### Before either switch

1. **Hold the launch lane.** Ask the session that owns petri's queue (today
   `petri-factory-on-gmktec`, under the fleet capacity coordinator) to pause
   launches. The hold counts only once every launch it made has LISTED in
   `fabro ps --server https://gmktec-xubuntu.perch-rudd.ts.net:32276`. A drive
   that has started but has no sandbox yet takes whichever provider the catalog
   names when its sandbox is created.
2. **Record the live pods**, so you can show the switch did not touch them:

   ```bash
   ssh cwoolley@gmktec-xubuntu.perch-rudd.ts.net \
     'KUBECONFIG=/etc/ci-runner/factory.kubeconfig kubectl get pods -n factory -o wide'
   ```

3. **Keep the two backends on the same image.** The Docker `image` you
   declare must equal `sandbox_providers.kubernetes.process_spec.image`, so a
   switch changes where the sandbox runs and not what is in it. The
   python-agent image has no `ENTRYPOINT` (its `Cmd` is `/bin/bash`). The
   plugin's pod `command:` override therefore skips no setup, and the pod keeps
   the image's `PATH`. Re-check this when the image changes:

   ```bash
   docker buildx imagetools inspect <image> --format '{{json .Image.Config}}'
   ```

   Measured 2026-10-31 for `python-agent-v1.136.2`: no Entrypoint, Cmd
   `["/bin/bash"]`, and `PATH=/root/.local/share/mise/shims:/root/.local/bin:...`.
   A sandbox that lacks a tool, for example `bunx`, lacks it on both backends.
4. Run the apply as the `ubuntu` user on `vps` (the Ansible control node), from
   a livespec-dev-tooling checkout of merged master, under the credential
   wrapper. The play refuses without `HONEYCOMB_INGEST_KEY_LIVESPEC`.

### Switch to Docker

1. In `host_vars/gmktec-xubuntu.yml`, on the `fabro-server` instance's
   `factory-python` entry, set `provider: docker` and add the image. Copy the
   tag from `sandbox_providers.kubernetes.process_spec.image`, which follows the
   orchestrator workflow pin:

   ```yaml
   - id: factory-python
     image: ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.136.2
     cpu: 4
     memory: 8GB
     provider: docker
   ```

   Set `provider: docker` explicitly. If you drop `provider` instead, the role
   keeps the catalog entry's existing `kubernetes` provider and refuses the
   image. Before livespec-dev-tooling PR #2990 the role refused even the
   explicit form, so the fallback could not be applied. The tested fallback
   found that defect.
2. Merge the change through a pull request.
3. Drift, then apply, limited to the factory host:

   ```bash
   /data/projects/1password-env-wrapper/with-livespec-env.sh \
     mise exec -- just ansible-drift ansible/fabro-hosts.yml --limit gmktec-xubuntu
   /data/projects/1password-env-wrapper/with-livespec-env.sh \
     mise exec -- just ansible-apply ansible/fabro-hosts.yml --limit gmktec-xubuntu
   ```

   The drift report names the disposition `environment factory-python is in the
   catalog with other settings and will be replaced`.
4. Verify the live pods you recorded are still `Running`. A sandbox already
   created keeps its backend, because the catalog only decides new sandboxes.
5. Release ONE launch. Confirm its sandbox is a container and not a pod:

   ```bash
   ssh cwoolley@gmktec-xubuntu.perch-rudd.ts.net 'docker ps --filter name=petri-<RUN-ID>'
   ssh cwoolley@gmktec-xubuntu.perch-rudd.ts.net \
     'KUBECONFIG=/etc/ci-runner/factory.kubeconfig kubectl get pods -n factory -l petri.run=<RUN-ID>'
   ```

### Switch back to Kubernetes

1. Restore the entry: drop `image`, and set `provider: kubernetes`.
2. Merge, drift, and apply exactly as above.
3. A Docker-backed run that is still in flight keeps its container and finishes
   on Docker. Leave it alone.
4. Release the next launch. Confirm it got a `petri-<run>-l0` pod in namespace
   `factory`, and that `docker ps` shows no container for it.

### Tested 2026-10-31

Both directions ran on 2026-10-31/11-01 inside one launch window. The fleet
coordinator `gitops-fleet-capacity-monitoring` scheduled it, and petri held its
lane throughout.

- **The fallback was not appliable until this test.** The role's base-entry
  refusal demanded a docker base entry, so `factory-python`, already on
  `kubernetes`, could not be declared back onto docker. livespec-dev-tooling
  PR #2990 (`8c518933`) fixed that.
- **Docker leg.** PR #2992 (`34410a19`) was applied at 23:36:19Z with
  `changed=1`, on the task "Replace this environment in the instance's
  catalog".
  - The live pods of runs `01M6A0F9NDRA` and `01M6A24KENJC` kept running
    through the PUT.
  - The window's one launch, `bd-ib-h23kbx` (run
    `01M6A675SGZWYDC816ZTE00EN5`, 23:46:15Z, no overrides), ran in Docker
    container `petri-01M6A675SGZWYDC816ZTE00EN5-l0` (`465b2a963791`, image
    `python-agent-v1.136.2`) on gmktec. Namespace `factory` held no pod for it
    (read at 23:57:18Z).
- **Kubernetes leg.** PR #2994 (`c2911fe3`) was applied from 00:20:16Z to
  00:48:49Z, again with `changed=1` on the factory-python replace.
  - The next launch, `overseer-yizu3e` (run `01M6A9H4K4PGT6VR0PBWPS697J`,
    launched 00:43:49Z), ran in pod `petri-01m6a9h4k4pgt6vr0pbwps697j-l0` on
    `poweredge-xubuntu`. It had 4 CPU and 7630Mi requests equal to limits, QoS
    Guaranteed. `docker ps -a` showed no container for it (read at 00:53:53Z).

**Recovery time.** Each switch costs one full
`fabro-hosts.yml --limit gmktec-xubuntu` apply, about 30 minutes. A drift run
before it takes 12 to 20 minutes more. The play has no environments-only path,
so a switch in either direction should be planned as roughly 45 minutes from
merge to converged catalog. The catalog PUT itself lands about two-thirds of the
way through the apply. Look for the line
`fabro-server on gmktec-xubuntu: environment factory-python ... will be replaced`
followed by `changed` on "Replace this environment in the instance's catalog".
The switch is in effect from that moment, even though the rest of the play
continues.

## 3. Rescuing a stranded pod-backed run

Use this procedure when a run died, was cancelled, or was reaped before its
work was published. That includes a server restart that cancels runs, a node
loss, and an operator `fabro rm`. Fabro's own needs-human exit already pushes
the implement commits to `refs/heads/needs-human/<run>`, so first check whether
the work is already on origin. Rescue only what is not there.

1. **Find out whether the work is already published.** Search the forge for a
   pull request or branch carrying the run id. Fabro stamps the id into its
   checkpoint commits. Then check the needs-human refs:

   ```bash
   git ls-remote origin 'refs/heads/needs-human/*' 'refs/heads/feat/<item>'
   ```

2. **Export the run's state** from the server. This works whether the pod
   exists or not:

   ```bash
   fabro dump <RUN-ID> --server https://gmktec-xubuntu.perch-rudd.ts.net:32276 -o <dir>
   ```

   Use the fleet client named in the governed repository's
   `dispatcher.factories.petri.bin`. The dump holds `run.json`,
   `events.jsonl`, `graph.fabro`, `stages/` and `checkpoints/`. A stage
   `diff.patch` exists only for UNCOMMITTED changes. The implement agent commits
   its own work under Red-Green-Replay, so the commits in the workspace are what
   you are rescuing.
3. **Locate the workspace.** The sandbox name is `petri-<run id lower-case>-l0`.
   If the pod still exists, its node is in `kubectl get pod -n factory -o wide`.
   If it does not, look for the directory on each worker:

   ```bash
   ssh cwoolley@poweredge-xubuntu.perch-rudd.ts.net 'ls /srv/factory-workspaces' | grep <run-id-lower>
   ```

4. **Fetch the run branch read-only** into a scratch bare repository on the
   control node. `git-upload-pack` runs on the worker, reads the workspace and
   changes nothing there. The workspace is root-owned, so `safe.directory` is
   passed to the remote side:

   ```bash
   git init --bare rescue.git && cd rescue.git
   git fetch --no-tags \
     --upload-pack='git -c safe.directory=* upload-pack' \
     cwoolley@<node>.perch-rudd.ts.net:/srv/factory-workspaces/<sandbox-name> \
     'refs/heads/fabro/run/<RUN-ID>:refs/heads/rescue/<RUN-ID>'
   git log --format='%h %s' rescue/<RUN-ID> | grep -v 'fabro(' | head   # the implement commits
   ```

   The same fetch works while the pod is still running, because the workspace
   is the same `hostPath` directory. It is the preferred route even for a live
   pod: `kubectl exec` would need write access to the sandbox, and this needs
   none.
5. **Push the rescued branch to origin** under `rescue/<RUN-ID>`. No CI workflow
   triggers on that ref pattern, because CI runs on pull requests and master
   pushes only:

   ```bash
   git push https://github.com/thewoolleyman/<repo>.git \
     refs/heads/rescue/<RUN-ID>:refs/heads/rescue/<RUN-ID>
   ```

6. Record the rescue ref on the work-item. Then re-dispatch, or open a pull
   request from the rescued commits.

**Demonstrated 2026-11-01 on genuinely unpublished work.** Run
`01M68640A8N82PEJKTTVG2J875` (`bd-ib-55vxu5`, orchestrator tenant) was a real
petri run in pod `petri-01m68640a8n82pejkttvg2j875-l0`. It was **cancelled**
(status `failed`, reason `cancelled`) after its implement and review_fix stages
had committed. That path writes no needs-human ref, so the run's last implement
commit, `598970f8a` ("fix: give the Codex judgement candidate a private home and
no profile hooks"), existed on no origin ref.

- `fabro dump` exported 244 files. On this cancelled run it took more than
  5 minutes, so give it a long timeout and do not read a slow dump as a hang.
- The read-only fetch from the retained workspace on `poweredge-xubuntu`
  recovered the run branch, tip `7be3238f`, which contains `598970f8a`.
- The push created `refs/heads/rescue/01M68640A8N82PEJKTTVG2J875`.
  `git branch -r --contains 598970f8a` now lists that rescue ref and nothing
  else.

An earlier run of the same procedure, on run `01M68T1WYT71N1TJJRHE8B3ARY`
(`bd-ib-nonaor`, rescue ref `rescue/01M68T1WYT71N1TJJRHE8B3ARY` at
`fe163cf1`), proved the mechanics. That run, however, had already reached the
needs-human exit, so its implement commits `199ddc0c` and `74f68369` were
already on origin at `needs-human/91e3cec80478470fa79e8c555f4d078e`. Step 1
exists for that reason: a run that ended at needs-human usually needs no rescue,
while a cancelled, reaped or infrastructure-killed run does.

**Shell note.** In zsh, `"$RUN:refs/..."` applies the `:r` modifier to `$RUN`
and mangles the refspec. Write `"${RUN}:refs/..."`, or spell the run id out in
full.

## 4. The cluster becomes unavailable while runs are in flight

The cluster's control plane is `poweredge-xubuntu`, and today it also runs every
factory pod. When it, its k3s, or the network to it is lost, the API server and
the pods' node go together.

What the plugin does, proven by `bd-ib-ad6dby` on the real cluster:

- While a sandbox's node is NotReady, the plugin reports the sandbox
  unavailable and creates no replacement pod.
- After a control-plane reboot, the same plugin process re-reads the refreshed
  kubeconfig and starts a sandbox created before the reboot again, on its
  original node, with its workspace contents intact.

The `hostPath` workspace survives a pod or k3s restart, but not the loss of the
node's disk.

What the operator does:

1. **Stop new work from piling up.** Ask the queue owner to hold petri's launch
   lane. Every new sandbox would fail to schedule.
2. **Establish what is down.** Read only:

   ```bash
   ssh cwoolley@gmktec-xubuntu.perch-rudd.ts.net \
     'KUBECONFIG=/etc/ci-runner/factory.kubeconfig kubectl get nodes'
   fabro ps --server https://gmktec-xubuntu.perch-rudd.ts.net:32276
   ```

3. **If the outage is short** (a reboot, or a k3s restart through
   `ansible/reboot-ci-server.yml` or `ansible/restart-k3s-agent.yml`), let the
   in-flight runs wait. The plugin resumes their sandboxes in place when the
   node returns. Do not cancel or `rm` them. Cancelling deletes nothing on disk,
   but it throws away a run that would otherwise have continued.
4. **If the outage will be long**, switch new work to Docker by following
   section 2. Docker sandboxes run on gmktec's own engine and do not need the
   cluster. Then release the hold. Runs already in flight stay where they are.
5. **For each in-flight run that cannot continue** (its stage timed out, or the
   node is gone for good):
   - If the node's disk is readable, rescue the run by following section 3, then
     cancel it.
   - If the disk is not readable, fall back to what the server holds: the work
     that reached origin through `needs-human/<run>` or the publish branch, and
     the `fabro dump` export. Search the forge for the run id before you assume
     anything is lost.
   - Then clear the ledger claim: `dispatcher.py reconcile-runs` in the governed
     repository, or `drive --action move:<id>:ready` for a 0 ms phantom.
     Re-dispatch afterwards.
6. **When the cluster is back**, switch the catalog back to Kubernetes by
   following section 2. Then release the lane and confirm the next launch got a
   pod.
