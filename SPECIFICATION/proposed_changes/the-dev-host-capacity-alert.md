---
topic: the-dev-host-capacity-alert
author: claude-opus-5-5
created_at: 2026-11-12T00:31:17Z
---

## Proposal: The dev host capacity alert can publish as an authenticated ntfy user and reports rate limiting

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Extend **Alert before full.** in §"Dev host disk retention": when the role is given an ntfy access token, the capacity check publishes as that user with the token as a bearer credential and never writes the token to a unit or log. Without one it publishes anonymously and logs that. A publication the server refuses as rate limited is logged as such and does not count as sent.

### Motivation

Measured on vmi3006760 by the dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4). The implementation item is livespec-dev-tooling-kvmjvm, which waits on this proposal; the filing screen's spec-change tier linked it to this topic. legacy-coordinator-agent asked for it on 2026-11-12.

- On 2026-11-11 the capacity check found /tmp above 75% and tried to publish every 15 min, 07:09-08:24Z and 21:24-23:24Z. Every attempt failed with HTTP 429. The last successful publication was 13:09Z. The maintainer got no alert while /tmp sat near 80%.
- `GET https://ntfy.sh/v1/account`, read 2026-11-12 00:25Z: role anonymous, limits basis ip, 250 messages a day, 250 used, 0 remaining. The check shares the host IP's anonymous quota with every other ntfy publisher on the host, chiefly the Claude Code notification plugin (630 idle-prompt notifications on 2026-11-11). On a busy day the alert goes silent exactly when the host is busiest.
- An authenticated user's quota is per user, not per IP, so the alert stops competing with anonymous publishers. Obtaining the account and projecting the token onto the host is a maintainer and secret step, so the anonymous path stays as the behaviour when no token is configured.
- The section says the check publishes and repeats no more than once per interval. It does not cover authentication, the token's handling, or what a rate-limited publication means for the repeat interval.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Dev host disk retention", in the paragraph that begins **Alert before full.**, insert after the sentence "The ntfy topic MUST be the host's `claude_ntfy_topic` inventory value.":

> When the role is given an ntfy access token, through a role variable documented in the role's `HOST_VARS.md` that names a file readable only by root, the check MUST publish as that authenticated user, sending the token as a bearer credential, and MUST NOT write the token into a unit file or a log. When no token is configured, or the named file is absent or empty, it MUST publish anonymously and log that it did so. A publication the server refuses as rate limited MUST be logged as rate limited, distinctly from any other failure, and MUST NOT count as sent, so the next check publishes again.
