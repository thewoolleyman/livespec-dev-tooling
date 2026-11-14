## The maintainer's statement of what done means

Prior intent: "I want to start doing this, so herdr panes on vps vs. hetzher or other machines don't have to directly type in panes and interrupt my direct interactions.  How can I enable and force this for all claude sessions on vps and hetzner-xubuntu and gamingpc-xubuntu?" Plan request: "Create a plan which will force this across the three machines, update all the relevant -info repos and gitops, roll it all aout and deply and test it, search and scrub and upcate all AGENTS.md with pointer to a new .ai/distributed-sendmessage-protocol, and then inform all active sessions, and do anything else that needs done.  The prior intent can be used as the definition of done."

## Definition of Done assertions derived from that statement

- On each of vps, hetzner-xubuntu and gamingpc-xubuntu, a root-owned /etc/claude-code/managed-settings.d/50-distributed-sendmessage.json sets remoteControlAtStartup to true and registers the pane-input guard hook, installed by that host's committed provisioning from a pin naming a livespec-dev-tooling release.
- A new interactive Claude Code session started on any one of the three hosts lists sessions on the other two hosts as Remote Control peers.
- A SendMessage sent from a session on one host to a named session on another host is delivered there, and that session's SendMessage reply arrives back at the sender.
- On each of the three hosts, a Claude Code Bash command that types literal text into a herdr pane hosting an agent is denied with a message naming SendMessage, while key-only send-keys and text input into a pane with no agent still run.
- livespec-dev-tooling master carries .ai/distributed-sendmessage-protocol.md, and the master AGENTS.md of every repository in research note 001's scope set points to it, with no remaining guidance telling an agent to type into another session's pane to message it.
- The global ~/.claude/CLAUDE.md on each of the three hosts carries the distributed SendMessage rule from committed host configuration.
- Every Claude Code session live on the three hosts at rollout time received a SendMessage announcing the protocol.

# 001 — Charter: distributed SendMessage across the interactive hosts

## Goal

Claude Code sessions on `vps`, `hetzner-xubuntu` and `gamingpc-xubuntu` talk to
each other with the built-in `SendMessage` tool, across machines, instead of
typing into each other's herdr (or tmux) panes. Pane typing interrupts the
maintainer's own direct interaction with a session, so it is to be FORCED off,
not merely discouraged.

## Measured starting state (2026-11-14, from hetzner-xubuntu)

- Claude Code 2.1.325 on vps and hetzner-xubuntu (`claude --version`);
  gamingpc-xubuntu has it at `~/.local/bin/claude` (not on the non-login PATH).
- `claude auth status` on hetzner-xubuntu: `authMethod: claude.ai`, Max plan.
  No `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BASE_URL` in the
  session environment on vps or gamingpc either.
- No `/etc/claude-code/` on any of the three hosts. No `remoteControlAtStartup`
  in any user settings file or any `~/workspace/*/.claude/settings*.json`.
- `ListAgents` from hetzner-xubuntu lists only same-machine peers: no session on
  any host is Remote Control connected today.
- `sudo -n true` succeeds as `ubuntu` on all three hosts.
- herdr exposes `pane send-text`, `pane send-keys` and `pane run` (text + Enter);
  `herdr pane get/list` reports an `agent` field (`claude`, ...) for a pane
  hosting an agent, and the env carries `HERDR_PANE_ID` for the caller's own pane.

## Mechanism (Claude Code docs, verified 2026-11-14)

- Cross-machine `SendMessage` is relayed through Anthropic Remote Control; a
  session on another machine is listed (label `Remote Control`) only when BOTH
  sides are Remote Control connected. Same-machine messages stay on a local
  socket. Needs claude.ai auth; API keys, `apiKeyHelper`, a non-Anthropic
  `ANTHROPIC_BASE_URL`, and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` block it.
  Versions: 2.1.224 messaging, 2.1.225 starting a cross-machine conversation.
- `remoteControlAtStartup: true` connects every interactive session at startup.
  Linux managed settings: `/etc/claude-code/managed-settings.json` plus the
  `managed-settings.d/` drop-in directory. A managed `true` beats a user
  `false`; a PROJECT/LOCAL `false` still wins (documented exception), and
  nothing stops an in-session `/remote-control` disconnect.
- No setting makes Claude prefer SendMessage; enforcement has to be a hook.
- `disableRemoteControl` is the kill switch — never set it.
- `-p` headless sessions are not covered by auto-start.

## Decisions (session-decided, reported for objection)

1. **Force via managed settings, not user settings.** A managed drop-in
   `/etc/claude-code/managed-settings.d/50-distributed-sendmessage.json` sets
   `remoteControlAtStartup: true` and registers the pane-input guard hook, so a
   user settings rewrite (Claude Code re-serializes `settings.json`) cannot drop
   either. This is a NEW root-owned surface, distinct from vps-info's
   `services/claude-config` (which owns user-level keys and is no-sudo by
   ruling); that ruling is about the user file and is left intact.
2. **One shared Ansible role** `claude_distributed_sendmessage` in
   livespec-dev-tooling `ansible/roles/`. REVISED during the session: this
   repository's own inventory (`ansible/inventory/legacy.yml`) already governs
   vps (`dev_hosts`, local connection) and gamingpc-xubuntu (`ci_pool`), so a
   new group `interactive_claude_hosts` and playbook `ansible/claude-messaging.yml`
   converge both from the dev host; vps-info and gamingpc-xubuntu-info need only
   their AGENTS.md pointer, not installers of their own. hetzner-xubuntu-info
   consumes the role at its exact `provisioning/livespec-dev-tooling.pin`, the
   pattern its `host-ansible.sh` already uses.
   The rule text also goes into the MANAGED `/etc/claude-code/CLAUDE.md`
   (verified: every session loads it, before user and project memory), not
   into each account's `~/.claude/CLAUDE.md`, which three different owners
   write today. The drop-in also sets `crossSessionInbound: accept`: unset,
   a permission-mode mismatch HOLDS a message behind an approval dialog, which
   is the interruption this plan removes.
3. **The guard (`pane-input-guard.py`)**, a PreToolUse Bash hook with a
   self-test corpus, DENIES literal text input into a pane that hosts an agent:
   `herdr [--machine X|--remote X|--session X] pane send-text|run <pane> ...`
   and `herdr agent prompt` when `herdr pane get <pane>` reports a CLAUDE
   agent (REVISED: Codex and pi seats cannot receive SendMessage, so their
   pane stays their channel and the guard allows it), and fails CLOSED when the
   lookup cannot be made. Its deny message names `SendMessage` and `ListAgents`.
   ALLOWED: `pane send-keys` (key names only: picker/escape unblocking, which
   SendMessage cannot do), input into the caller's own pane, input into a pane
   with no agent (starting a new session in a fresh shell pane), `pane read`,
   `wait-output`. `tmux send-keys` carrying literal text (`-l`, or any argument
   that is not a tmux key name) is denied outright: tmux is a retired transport.
   Raw `herdr api` socket calls are out of scope (guardrail, not a sandbox).
4. **Protocol doc** `.ai/distributed-sendmessage-protocol.md` lives canonically
   in livespec-dev-tooling; every fleet repo's AGENTS.md (and the always-load
   CLAUDE.md copies that carry the progressive index) points to it by GitHub
   URL, and guidance that tells an agent to type into another Claude session's
   pane to message it is rewritten to SendMessage.
5. **Session naming.** Cross-machine addressing is by session name with no
   machine prefix; the protocol tells sessions to `/rename` to a unique name.

## Scope: AGENTS.md set

Repos with an AGENTS.md cloned on hetzner-xubuntu (2026-11-14): 1password-env-wrapper,
agent-cockpit-info, dolt-server, gamingpc-xubuntu-info, herdr-info,
hetzner-xubuntu-info, homelab, livespec, livespec-console-beads-fabro,
livespec-dev-tooling, livespec-driver-claude, livespec-driver-codex,
livespec-driver-pi, livespec-orchestrator-beads-fabro,
livespec-orchestrator-git-jsonl, livespec-overseer, livespec-runtime,
livespec-website, openbrain, tailscale-admin, vps-info.

## Maintainer's words (verbatim DoD source)

See the plan epic's Definition of Done and the statement recorded with it.
