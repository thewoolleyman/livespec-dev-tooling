# Gate runner — the SECOND, PRIVILEGED runner trust tier

The sibling `ci-runner/` tree provisions the **contained** CI runner: a
`ci-runner` user in none of `docker`/`sudo`/`dolt`, jobs forced into a
rootless container with the host docker socket stripped, host-loopback
services unreachable. That containment is exactly why it **cannot** run
the orchestrator's live golden-master gate.

The golden-master gate (`livespec-orchestrator-beads-fabro`'s
`.github/workflows/acceptance-live-golden-master.yml`) does what the
operator does by hand: it drives **Docker** (the DinD orchestrator
container plus volumes — Docker access on this host is root-equivalent),
reads the host **Codex credential** (`~/.codex/auth.json`), runs the host
**`fabro`** binary, and needs four 1Password secrets — including an
org-scoped token that **creates and deletes GitHub repos**. Every one of
those is a thing the contained lane deliberately denies.

So the gate needs a genuinely privileged runner, and the containment
therefore cannot come from confining the runner. **It comes from
controlling what is allowed to reach it.**

## The containment: on-demand, trigger-verified minting

**No privileged runner idles.** Nothing is registered and nothing is
listening. A GitHub Actions job cannot claim a runner that does not exist.

The supervisor polls the gate repo for a **queued** run and mints exactly
one single-use runner only when the run passes **every** trust check:

| Check | Required value | Why |
|---|---|---|
| `run.path` | `.github/workflows/acceptance-live-golden-master.yml` | Only the gate workflow — no other workflow in the repo can obtain a privileged runner. |
| `run.event` | `repository_dispatch` **or** `workflow_dispatch` | Both require a token/actor with **write** access. Neither is reachable from a fork. |
| `run.head_branch` | `master` | The code that runs is reviewed, merged master code. `repository_dispatch` always uses the default branch. |

A fork PR's run carries `event == "pull_request"`, so it never matches — it
queues harmlessly and expires with no runner minted. This is a
discrimination the **runner label alone cannot make**: a label is a request
any workflow may write, whereas the supervisor inspects the *event and
workflow identity* before granting compute.

Belt-and-braces: `livespec-orchestrator-beads-fabro`'s fork-PR approval
policy is `all_external_contributors` (the strictest), matching `livespec`.

After the single job, the JIT runner **auto-deregisters** and the host
returns to having no privileged runner.

## Identity: the operator, deliberately

`gate-runner@.service` runs as **`ubuntu`** — the operator. That is not
laziness: the gate workflow is *specified* against the operator's
environment (`$HOME/.fabro/bin/fabro`, `~/.codex/auth.json`,
`/data/projects/1password-env-wrapper/with-livespec-env.sh`,
`/data/projects/...` checkouts).

A dedicated user would buy **no** isolation here — it would still need the
`docker` group, and docker-group membership is root-equivalent — while it
*would* force duplicating the host Codex subscription credential. Copying a
secret to gain nothing is a net loss. The trust boundary is the trigger
surface above, not the uid.

## Files

| Path | Role |
|---|---|
| `gate-runner-supervisor.sh` | The on-demand, trigger-verified minter. Polls the gate repo; mints ONE JIT runner per trusted queued run; waits; repeats. Runs as `ci-sup`, the only account that reads the App key. |
| `gate-runner@.service` | One ephemeral privileged runner. Fixed `User=ubuntu`, fixed `ExecStart`, no container hooks (gate steps run directly on the host). |
| `gate-runner-supervisor.service` | The supervisor unit, under the `github-ci-runners` 1Password environment. |
| `50-gate-runner-supervisor.rules` | polkit: `ci-sup` may start/stop `gate-runner@*.service` and nothing else. |
| `app-installation-token.sh` | Prints a short-lived App installation token (the poll credential). |
| `provision-gate-runner.sh` | Idempotently installs the runner, units, polkit rule, and scripts. |
| `trigger-surface-exit-tests.sh` | Proves the discrimination: trusted events mint, `pull_request` never does. |

## GitHub-side prerequisites

- The `thewoolleyman-ci-runners` App (installation `146033367`) must include
  `livespec-orchestrator-beads-fabro` — `administration: write` is what
  `generate-jitconfig` needs. **This is a maintainer click**; a PAT cannot
  modify an App installation.
- **No `Actions: Read` grant is needed.** The gate repo is public, so its
  workflow-run list is readable with the existing installation token
  (verified: HTTP 200 cross-repo).

## Nature

Host operational artifacts (shell, systemd units, polkit) — not Python
product code, so not part of the `just check` aggregate. Recreatability is
the contract: re-running `provision-gate-runner.sh` converges a fresh host,
and `trigger-surface-exit-tests.sh` proves the trust boundary still holds.
The design home is the **livespec** repo,
`plan/fabro-ci-image-factoring/phase0-runner-containment-design.md`
§"Second trust tier — the privileged gate runner".
