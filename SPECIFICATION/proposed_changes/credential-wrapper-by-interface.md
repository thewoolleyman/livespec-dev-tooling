---
topic: credential-wrapper-by-interface
author: claude-opus-5-5
created_at: 2026-11-15T05:26:22Z
---

## Proposal: Name the reconcile-mode secret source as the project-configured credential wrapper environment

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The fleet-member reconcile mode says secrets are pushed from the `1Password-wrapper environment`. Name it the project-configured credential wrapper environment, and state that Parameter Store is the canonical family source while consumers keep the installed wrapper contract through staged conversion. The env→stdin GitHub projection, the source and destination names, and secret-free output are unchanged.

### Motivation

livespec v249 (thewoolleyman/livespec#3252, non-functional-requirements.md fleet-secrets section) makes AWS Systems Manager Parameter Store the single canonical source for fleet secrets, including the GitHub App credentials this mode projects, makes the livespec 1Password Environment a temporary downstream copy, and keeps `/usr/local/bin/with-livespec-env.sh` and its calling convention for callers while only its backend changes at each host's conversion. No host has converted, so the contract names the interface and the canonical owner rather than a backend. Plan epic overseer-iyfjbo, change-plan entry T04. The dependent diagnostic change (entry N07) is held in a separate draft PR until this proposal is revised.

### Proposed Changes

In `SPECIFICATION/contracts.md`, in the **Reconcile mode** bullet of the fleet-member wiring contract:

1. Replace

```
secrets pushed from the 1Password-wrapper environment (source env vars
```

with

```
secrets pushed from the project-configured credential wrapper environment (source env vars
```

2. Replace

```
MUST be invoked under `with-livespec-env.sh` so the secret projection is present.
```

with

```
MUST be invoked under `with-livespec-env.sh` so the secret projection is present. AWS Systems Manager Parameter Store is the canonical family source of the projected values, per livespec core's fleet-secrets rule; consumers retain the installed wrapper contract (`/usr/local/bin/with-livespec-env.sh --`, unchanged path and calling convention) through each host's staged conversion, and this mode neither reads Parameter Store directly nor assumes any host has converted.
```

No other text in the bullet changes; no new runtime backend requirement is introduced.

## Proposal: Ledger reach names the installed wrapper and drops the Keychain clause

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

The Ledger reach rule says the tenant credential comes through `the 1Password environment wrapper`, which on macOS reads its token through the Keychain. Name only the installed wrapper path and drop the backend-specific Keychain clause. The tunnel, the committed loopback address and tenant isolation are unchanged; no AWS reader or Darwin seal is required before a host converts.

### Motivation

livespec v249 (thewoolleyman/livespec#3252) keeps `/usr/local/bin/with-livespec-env.sh` and its calling convention while its backend becomes homelab's shared-credentials launcher at each host's conversion. The 1Password and Keychain wording describes one backend that is being replaced; the interface sentence stays true before and after conversion. Plan epic overseer-iyfjbo, change-plan entry T05.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, in the **Ledger reach.** paragraph, Replace

```
The tenant credential MUST come through the 1Password environment wrapper, `/usr/local/bin/with-livespec-env.sh`, which on macOS reads its token through the Keychain. It MUST NOT come from a credential file copied from another host.
```

with

```
The tenant credential MUST come through `/usr/local/bin/with-livespec-env.sh`. It MUST NOT come from a credential file copied from another host.
```

No other text in the paragraph changes.
