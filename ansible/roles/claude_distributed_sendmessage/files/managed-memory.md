## Messaging another agent session: SendMessage, never pane typing

To ask, tell or answer another Claude Code session -- on this machine or on
another fleet host -- use the `SendMessage` tool. Run `ListAgents` first;
sessions on other machines appear labelled `Remote Control`, and the session
name is the address (no machine prefix). Give your own session a unique name
with `/rename` so peers can address you.

Never type a message into another Claude session's terminal pane (`herdr
pane send-text`, `herdr pane run`, `herdr agent prompt`, `tmux send-keys
<text>`): it lands in the line the maintainer is typing into. A managed
PreToolUse hook denies those commands against a pane that hosts a Claude
agent. Key-only input (`herdr pane send-keys <pane> esc`) to unblock a picker
stays allowed, and Codex or pi seats, which cannot receive SendMessage, are
still reached through their pane.

A successful send means delivered, not read or acted on; never treat silence
as agreement. Full protocol:
https://github.com/thewoolleyman/livespec-dev-tooling/blob/master/.ai/distributed-sendmessage-protocol.md
