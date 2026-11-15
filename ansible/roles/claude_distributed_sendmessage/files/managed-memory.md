## Messaging another agent session: prefer SendMessage

To ask, tell or answer another Claude Code session -- on this machine or on
another fleet host -- use the `SendMessage` tool by default. Run `ListAgents`
first; sessions on other machines appear labelled `Remote Control`, and the
session name is the address (no machine prefix). Give your own session a
unique name with `/rename` so peers can address you.

Prefer SendMessage over typing a message into another session's terminal pane
(`herdr pane send-text`, `herdr pane run`, `herdr agent prompt`, `tmux
send-keys`): typed text lands in the line the maintainer may be typing into.
Typing into a pane is still ALLOWED and nothing blocks it. Use it when it is
the right tool: a slash command such as `/remote-control`, answering a picker,
a session SendMessage cannot reach, or a Codex or pi seat. Check the pane is
idle first, and keep it short.

A successful send means delivered, not read or acted on; never treat silence
as agreement. Full protocol:
https://github.com/livespec-ai/livespec-dev-tooling/blob/master/.ai/distributed-sendmessage-protocol.md
