# Distributed SendMessage protocol

Read this before you message, ask, notify, direct or answer another agent
session (a Claude Code one; Codex and pi seats are covered below), on this machine or on another fleet host. Read it also before you run
`herdr pane send-text`, `herdr pane run`, `herdr agent prompt` or
`tmux send-keys` against a pane you did not create, and before you diagnose a
`BLOCKED: ... Typing into another agent session's pane` hook denial.

## The rule

**Agent sessions talk to each other with Claude Code's `SendMessage` tool, never
by typing into each other's terminal panes.** Text typed into a pane lands in
the same input line the maintainer may be typing into. It interrupts their
direct interaction with that session, and it can corrupt both inputs. The
maintainer ruled this on 2026-11-14 (plan `distributed-sendmessage`, epic
`livespec-dev-tooling-rlwppp`).

## How to send

1. Run `ListAgents`. It lists sessions on this machine, and sessions on other
   machines labelled `Remote Control`.
2. Call `SendMessage` with `to` set to the session's name, exactly as the
   listing prints it. There is no machine prefix. Append the ` [ref]` only when
   two rows share a name or an error asks you to.
3. Put a self-contained first line in `message`. The receiving human sees
   only that line until they expand the message.
4. To reply to a message you received, copy its `from` attribute into `to`.

Give your own session a unique, descriptive name with `/rename` (or `--name`
at launch) so peers can address you. A seat named after its plan or role is
best. Unnamed sessions get a generated name, which is hard to address across
machines.

## What a successful send means

The message reached the session's inbox, and it drains at that session's next
tool round. That is delivery, not that anyone read it or acted on it. For a
session on another machine, nothing reports back. **Never treat silence as
agreement.** When you need a result, ask for a reply. If it matters, record the
request where the work is tracked (for example a relay on the plan epic).
Waiting on a peer is not a reason to type into its pane.

To hear when a session on THIS machine goes idle, use
`SendMessage(notify_when_idle: true)` and don't poll `ListAgents`.

## What is enforced, and where

On every interactive host (`vps`, `hetzner-xubuntu`, `gamingpc-xubuntu`), a
root-owned Claude Code managed-settings drop-in,
`/etc/claude-code/managed-settings.d/50-distributed-sendmessage.json`, sets:

- `remoteControlAtStartup: true`. Every interactive session joins Remote
  Control, so the other hosts can list it and message it.
- `crossSessionInbound: accept`. This stops a permission-mode mismatch between
  sender and receiver from holding a message behind an approval dialog. That
  dialog would be the same interruption this protocol removes.
- A PreToolUse Bash hook, `/usr/local/lib/claude-code/pane-input-guard.py`. It
  DENIES:
  - `herdr pane send-text`, `herdr pane run` or `herdr agent prompt` into a
    pane where herdr reports a CLAUDE agent (including with `--machine`,
    `--remote` or `--session`). It fails closed when it cannot look the pane up.
  - `tmux send-keys` that carries literal text.

  It ALLOWS:
  - key-only input (`herdr pane send-keys <pane> esc`, `tmux send-keys -t x
    Escape`), which unblocks a picker or dialog that SendMessage cannot reach;
  - input into your own pane;
  - input into a pane with no agent, such as starting a new session in a fresh
    shell pane;
  - input into a NON-Claude agent (Codex, pi). Those harnesses cannot receive
    SendMessage, so their pane remains the channel to them. Send the text, then
    `send-keys Enter`, and mirror anything durable as a ledger comment;
  - every read (`pane read`, `wait-output`, `agent read`).

The rule is also carried in the managed `/etc/claude-code/CLAUDE.md`, which
every session loads.

The provisioning that installs this:

- vps and gamingpc-xubuntu: this repository's role
  `ansible/roles/claude_distributed_sendmessage`, applied by
  `just ansible-apply ansible/claude-messaging.yml` from the dev host. The
  hosts are the inventory group `interactive_claude_hosts`.
- hetzner-xubuntu: `hetzner-xubuntu-info` consumes the same role at its
  `provisioning/livespec-dev-tooling.pin`.

Re-applying is the repair path. Don't hand-edit `/etc/claude-code/`.

## When a session is not reachable

- **It is not listed.** A session on another machine appears only when both
  sides are connected to Remote Control. A session started before the rollout
  needs a restart, or `/remote-control` run inside it. A session authenticated
  by `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `apiKeyHelper`, a
  non-Anthropic `ANTHROPIC_BASE_URL` or
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` cannot join Remote Control. That
  includes most headless factory workers.
- **It is a headless `-p` worker.** Auto-start does not cover it. Reach it
  through the work-item ledger or its own transport (factory runs read their
  brief; see `.ai/fabro-dispatch-diagnosis.md`), not through its pane.
- **A project opts out.** A project-level `.claude/settings*.json` with
  `remoteControlAtStartup: false` overrides the managed `true`, as documented.
  No fleet repository may commit one. Treat finding one as a defect.

- **It runs on a Mac.** The Macs are outside this rollout. A Claude seat there
  joins only when its user settings enable Remote Control (`/config`, then
  "Enable Remote Control for all sessions"). Until it does, the guard still
  refuses to type into it, so reach it by a ledger comment on the item or plan
  it owns, and name it as unreachable in your report.

If none of these applies and SendMessage still cannot reach a session, report
it to the maintainer or the coordinator. Do not fall back to typing into the
pane.

## Privacy and routing

Messages between machines are relayed through Anthropic's Remote Control
service, not over the tailnet. Messages between sessions on the same machine
stay on a local socket. Never put a secret in a message.
