---
topic: checks-leave-no-gpg-daemon
author: claude-opus-5-5
created_at: 2026-11-12T06:38:15Z
---

## Proposal: Checks and their tests leave no gpg daemon behind

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a paragraph to §"Enforcement-suite invocation", after **Check runners leave no coverage directories behind.**. A check this repository ships that gives gpg a private temporary GNUPGHOME stops every gpg daemon started for that home before removing it. Test fixtures that make throwaway GNUPGHOMEs record their creator, and before making a new one they reclaim homes, and their daemons, whose creator is gone. All of this is best-effort and never changes a verdict.

### Motivation

Implementation item livespec-dev-tooling-hlyayb, under the dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4). Its launch-time preflight refused it twice, at 05:58:37Z and 06:30:31Z on 2026-11-12, because no spec heading governs its assertions.

- On vmi3006760 at 2026-11-12 00:45Z, 15 orphaned `gpg-agent --homedir /tmp/... --daemon` processes from dead sessions were running, dated 2026-10-24 to 2026-11-11. Five came from the red-green-replay revert check's temporary `rgr-forge-trust-*` GNUPGHOME: the check removes the directory and leaves the agent gpg auto-started there. Ten came from that check's test fixtures (`rgr-forge-key-*`) when a pytest session was killed before teardown. poweredge-xubuntu and gmktec-xubuntu showed the same orphans.
- Each orphan inherits the gate's `CLAUDE_CODE_SESSION_ID`, so the dev host retention counts its dead session as live, and that session's scratch is never removed. On 2026-11-12, 2.2G of /tmp was pinned that way.
- Note on daemon parentage: `gpg-agent --daemon` reparents to pid 1 even while it is in use. So a parent of pid 1 does not mark an orphan; a recorded creator does.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Enforcement-suite invocation", insert this paragraph directly after the paragraph that begins **Check runners leave no coverage directories behind.**:

> **Checks leave no gpg daemon behind.** A check this repository ships that runs gpg under a private temporary `GNUPGHOME` MUST stop every gpg daemon started for that home before it removes the home, whatever the check concludes. A test fixture this repository ships that makes a throwaway `GNUPGHOME` MUST record in it the pid of the process that created it and that process's start time. Before the fixture makes a new one, it MUST stop the gpg daemons of, and remove, every such home under the system temp directory whose recorded creator is no longer running; a pid now held by a different process does not count as the creator. It MUST also stop every gpg daemon whose home no longer exists, but only a daemon whose home lies under the system temp directory and matches a home-name pattern this repository's checks and fixtures create (`rgr-forge-key-*`, `rgr-forge-trust-*`), and MUST leave in place every home whose recorded creator is still running, together with its daemons. Stopping and reclaiming are best-effort: a failure is logged, and no check's or test's verdict depends on it.
