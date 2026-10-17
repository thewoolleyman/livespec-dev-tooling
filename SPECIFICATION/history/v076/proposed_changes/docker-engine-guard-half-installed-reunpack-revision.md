---
proposal: docker-engine-guard-half-installed-reunpack.md
decision: accept
revised_at: 2026-10-17T22:03:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:petri-factory-on-gmktec
---

## Decision and Rationale

Accepted on the maintainer's explicit approval (2026-10-17, petri-factory-on-gmktec session: "Yes if this proposal will fix it, then I accept it. Just get it done."). The Package fence recovery sentence previously aimed `dpkg --configure` at a `half-installed` leftover, which dpkg documents as needing reinstallation and refuses (`cannot configure (current status 'half-installed')`), so a kill landing in an intended package's unpack stranded the run (FAULTS B-06 and M-04 at v1.112.10, guard-vm-0 and guard-vm-2). Recovery now re-unpacks such a package from this run's own audited `.deb` matched by name, version and architecture, refuses when none matches, and configures only unpacked or half-configured leftovers; `dpkg --unpack` is confined to audited archives. Measured on guard-vm-1: re-unpack then configure-by-name leaves docker.io, runc and containerd installed with `dpkg --audit` empty. Design record F6 (a fresh transaction starts from an empty dpkg --audit) is preserved. Implementation is owned by livespec-dev-tooling-eyfhky (guard child 15).

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-17T22:03:00Z
verdict: NO BLOCKERS
proposal_stem: docker-engine-guard-half-installed-reunpack
content_digest: 46e17ac0a79e7ec011695142f197131e615a7b5ff46f638c0ff1d8cc5ee72b16
