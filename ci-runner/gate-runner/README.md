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
| `hosted-only.conf` | systemd drop-in for the supervisor unit carrying `ConditionPathExists=/run/livespec-local-ci-enabled` — the compensating control for the hosted-only posture (see below). Installed by `provision-gate-runner.sh` into `/etc/systemd/system/gate-runner-supervisor.service.d/`. |
| `gate-optin.sh` | THE sanctioned operator opt-in act: creates `/run/livespec-local-ci-enabled` (refusing if one exists — `--renew` is the explicit, logged alternative; `--revoke` removes it and stops the supervisor) and starts the supervisor. Installed to `/usr/local/lib/ci-runner/`. |
| `gate-optin-expiry.sh` | The 24h expiry enforcer: removes an opt-in older than 24h from its creation, logs creation time and age, and stops the supervisor. It never creates or refreshes the opt-in. |
| `gate-optin-expiry.service` / `.timer` | Oneshot + 15-minute timer driving `gate-optin-expiry.sh`. Enabled by `provision-gate-runner.sh`, which also runs one pass immediately. |
| `50-gate-runner-supervisor.rules` | polkit: `ci-sup` may start/stop `gate-runner@*.service` and nothing else. |
| `app-installation-token.sh` | Prints a short-lived App installation token (the poll credential). |
| `mint-jitconfig.sh` | Mints one JIT runner registration from the App credential. `gate-runner-supervisor.sh` EXECUTES this at mint time, so it is a RUNTIME dependency of this tier. Moved here from `../supervisor/` under `livespec-s43svm.19`, which has since deleted that tree — leaving it there would have removed a script a running service calls. |
| `provision-gate-runner.sh` | Idempotently installs the runner, units, the hosted-only drop-in, the opt-in expiry timer, polkit rule, and scripts, and creates the `ci-sup` supervisor identity. It does NOT create the `github-ci-runners` group: membership is what makes the App private key readable, so that stays an explicit operator act, checked rather than assumed. |
| `trigger-surface-exit-tests.sh` | Proves the discrimination: trusted events mint, `pull_request` never does. |

## Hosted-only posture: the supervisor is gated behind an opt-in

The supervisor unit is gated behind
`ConditionPathExists=/run/livespec-local-ci-enabled` via the
`hosted-only.conf` drop-in. `systemctl enable --now` therefore records the
boot wiring but **skips the start** until an operator creates the opt-in
with `sudo /usr/local/lib/ci-runner/gate-optin.sh` (which also starts the
supervisor). That drop-in was hand-applied on the live host and committed
here under `livespec-s43svm.43`, which also tracks whether this tier
belongs on the factory host at all; nothing here presumes an answer.

### Opt-in expiry

livespec `SPECIFICATION/non-functional-requirements.md` §"Fleet CI
execution posture" (v214, ratified under `livespec-s43svm.43`) obliges:
the opt-in "MUST carry a wall-clock expiry enforced on the host of no more
than 24 hours from the opt-in's creation, and an opt-in MUST NOT be
extended, renewed, or re-created by anything other than a fresh explicit
operator act"; "a gate supervisor found active with no opt-in present, or
with an opt-in past its expiry, is a violation". The drop-in's
"reboot-ephemeral" comment was never a bound on a long-uptime host — a
nine-day-old opt-in was measured on the live host on 2026-08-23 — and is
now backed by a real one:

- **Ceiling: 24h from creation.** `gate-optin-expiry.timer` runs
  `gate-optin-expiry.sh` every 15 minutes (worst-case enforcement
  24h15m). It measures the file's birth time (`stat -c %W`; mtime only
  if the filesystem reports no birth time, and the journal says which).
  Past the ceiling it **removes the opt-in, logs the creation time and
  age, and stops `gate-runner-supervisor.service`** — the explicit stop
  is required because systemd evaluates `ConditionPathExists` only when
  a start is attempted; a running unit is not stopped by its condition
  later becoming false. Stopping mid-run is safe: a gate job runs in its
  own `gate-runner@<name>.service`, which the supervisor merely waits on,
  so the job completes and auto-deregisters regardless.
- **No renewal by anything but an operator.** The expiry service never
  creates or touches the opt-in. The writer set is exactly
  `gate-optin.sh`, which refuses to create an opt-in that already exists;
  `--renew` removes and re-creates it (a new explicit act, logged with
  `logger -t gate-optin`), so the 24h window restarts from a new birth
  time and the journal records who renewed and when. **Hand-`touch`ing
  `/run/livespec-local-ci-enabled` is not a sanctioned path** — it
  bypasses the no-silent-renewal refusal and leaves no record.
- **Absent opt-in + active supervisor is the other violation shape.**
  The expiry pass also stops a supervisor found active with no opt-in.

`provision-gate-runner.sh` installs the units and script, enables the
timer, and runs one expiry pass immediately, so re-provisioning a host
that carries an over-age opt-in converges to the gated state in that same
run.

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
