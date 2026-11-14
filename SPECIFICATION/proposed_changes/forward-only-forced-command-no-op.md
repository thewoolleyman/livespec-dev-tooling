---
topic: forward-only-forced-command-no-op
author: claude-opus-5-5
created_at: 2026-11-14T03:00:51Z
---

## Proposal: A forward-only entry's do-nothing forced command may block

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Clarify the forward-only authorized_keys rule: the required command is a forced command that does nothing. It may be `/bin/false` or a session-bound blocking no-op such as `/usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity`. In both cases the key yields no shell and runs no work. This only clarifies wording: the existing scenario's 'a command that does nothing' already covers both forms, and no behavior changes.

### Motivation

livespec-dev-tooling#4620 changes the hetzner-xubuntu Dolt-tunnel entry's forced command from `/bin/false` to `/usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity`. The tunnel can then open a session, which makes OpenSSH 10.0 on vps set TCP_NODELAY (hetzner-xubuntu-info research note 024: bd show from 18.8 s to about 10.6 s). The coordinator ruled that #4620 conforms to the current wording. Still, 'runs no command' could be read as excluding any process that stays alive, so this proposal states the intended reading in parallel with #4620, without blocking it.

### Proposed Changes

In `non-functional-requirements.md`, the forward-only authorized_keys paragraph MUST replace its second sentence as follows. The rest of the paragraph is unchanged.

```diff
-It MUST carry `restrict`, MUST enable only port forwarding, and MUST carry a command that does nothing, so the key yields no shell and runs no command.
+It MUST carry `restrict`, MUST enable only port forwarding, and MUST carry a forced command that does nothing, so the key yields no shell and runs no work: for example `/bin/false`, or a session-bound blocking no-op such as `/usr/bin/setpriv --pdeathsig KILL /usr/bin/sleep infinity`. The forced command replaces any command the client asks for, so no client-chosen command ever runs. A session-bound no-op ends when its sshd parent exits, so a dropped connection leaves no process behind.
```

The reasoning behind the example MAY sit next to the role that writes the entry (`ansible/roles/authorized_keys_managed/HOST_VARS.md`), not in this paragraph:
- A forwarding client that must open a session cannot use `/bin/false`, which ends the session at once. On OpenSSH 10.0, a session is needed for sshd to set `TCP_NODELAY` on the connection.
- sshd does not kill a no-pty session's child when the connection drops, which is why the blocking form is tied to its sshd parent.
