# Durable ledger mailbox as the default cross-machine seat channel

Item livespec-dev-tooling-laor2c; plan remote-control-retirement (epic livespec-dev-tooling-s63cb5), plan assertion 4.
Written 2026-11-21 by the remote-control-retirement seat. Status: DESIGN, awaiting the maintainer's answer to the one question at the end.

## Problem

Remote Control was the cross-machine channel between seats. It deadlocked fifteen seats at 2026-11-21 ~00:09Z: an account rotation raised an Enter-to-select dialog in every seat, no seat could answer it, and the only repair was a human pressing Continue. Typing into another seat's pane is the fallback, but it lands in whatever the maintainer is typing, and it only reaches seats on the same herdr server. The replacement must not let one component failure leave seats waiting on a dialog nobody answers.

## Design

The mailbox is a table of messages in the shared beads/Dolt ledger the fleet already depends on. Nothing in it types into a pane and nothing in it raises a dialog.

- **Record.** One message per record: `from`, `to` (a seat name, as `ListAgents` names it), `urgency` (`normal` or `urgent`), `body`, `sent_at`, `read_at`, `read_by`. A message is addressed to a seat, not to a pane or a machine, so it survives a relaunch and works across hosts.
- **Send.** `mailbox send --to <seat> --urgency <u> <body>` writes the record through the ledger wrapper. It prints the record id, and fails loudly if the ledger refuses the write, so a sender never believes an undelivered message was sent.
- **Read.** A hook in each seat's harness runs at turn boundaries, calls `mailbox read --me <seat>`, injects every unread message into the seat's context, and stamps `read_at`. A seat that is mid-task sees the message at its next boundary; a seat that has stopped sees it at its next prompt.
- **Urgent.** A host service running outside any agent session, the same shape as the seat-dialog watchdog, polls for `urgent` messages unread past a dwell and raises the alarm through the watchdog's existing sinks: the journal, the alarm file, and a ledger comment on the coordinator epic. It alarms and never types, for the same reason the watchdog never answers an unknown dialog.
- **Typing stays where it is needed.** The maintainer's PANE-TYPING-ALLOWED ruling holds: slash commands and pickers still need a typed key. The mailbox is the default for messages, not a ban on typing.

## Why no single failure deadlocks the fleet

- Ledger down: `mailbox send` fails loudly at the sender; the sender holds the message and retries. No seat is left waiting on anything.
- Hook absent or broken in a seat: the message stays unread, the urgent poller alarms, and the maintainer or coordinator sees it out of band.
- Poller down: normal delivery is unaffected; only the urgent alarm is lost, and the existing watchdog journal check shows the poller's own liveness.
- No part of the channel raises a selection dialog, so the 2026-11-21 failure shape cannot arise from it.

## Behaviour under each answer to the delivery-timing question

- **A, asynchronous at the next turn boundary plus an out-of-band alarm for urgent messages (recommended).** The design above, unchanged.
- **B, also nudge the seat immediately.** The same store, plus an optional `wake` step in `mailbox send` that types a one-line nudge into the recipient's pane. The message is still the source of truth; the nudge is best-effort and may be dropped without losing the message. This reintroduces the typed-text interruption, which is why it is not the default.

The record, hook, poller and alarm are identical under both answers, so the first implementation child can be filed before the answer arrives.

## Open question for the maintainer (one question)

When a seat is working and a message arrives, should it be delivered at the seat's next turn boundary with an out-of-band alarm only for urgent messages (recommended: it never interrupts you or a seat mid-turn, and nothing it does can raise a dialog), or should urgent messages also type a nudge into the seat's pane?

## Follow-up children, not filed yet

1. The `mailbox` command and record schema in the ledger.
2. The seat read hook and its install on every dev host.
3. The urgent poller as a host role beside seat_dialog_watchdog.
