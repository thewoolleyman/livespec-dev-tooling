---
topic: a-shared-check-fails-a
author: claude-opus-5-5
created_at: 2026-11-15T16:19:26Z
---

## Proposal: A shared check fails a clone whose origin remote names a non-canonical repository owner

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a canonical per-commit check, `canonical_origin_owner` (`check-canonical-origin-owner`), that fails when the clone it runs in has an origin remote (fetch or push URL) that does not name the repository's canonical owner and repository in a form the expedited incident hook accepts. Its failure message names the URL found and the canonical URL expected, and gives the exact `git remote set-url origin <canonical URL>` command that repairs the clone. Add one scenario covering the fail, repair and pass path.

### Motivation

Work item livespec-dev-tooling-6iqhw6 (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol), filed on legacy-coordinator-agent's ruling of 2026-11-15. On 2026-11-15 ten fleet repositories moved from github.com/thewoolleyman to github.com/livespec-ai. The expedited incident hook (livespec_dev_tooling/incident_hook_process.py, exact_tree) compares remote.origin.url and the resolved push destination LITERALLY against the incident chain's canonical repository, and that compare stays strict: a redirect-trusting compare would weaken the chain's identity check. GitHub's redirect hides a stale origin from every other git command. So after the move, any clone whose origin still named thewoolleyman/<repo> refused every expedited commit and push ('incident-hook-refused: canonical repository does not match local origin'), and nothing surfaced the stale origin until an incident needed the clone. Measured on 2026-11-15: all ten moved repositories' primary clones on vmi3006760, and nine on hetzner-xubuntu, carried the old owner; they were re-pointed by hand. This check keeps clones from drifting back, and turns the repair into a printed one-line command on hosts that have no committed path managing their clones.

### Proposed Changes

In `SPECIFICATION/contracts.md`, add a new H3 section after §"`no_ambient_environment_loops` check":

```
### `canonical_origin_owner` check

Invocation: `python -m livespec_dev_tooling.checks.canonical_origin_owner`, wired as the `check-canonical-origin-owner` recipe, run from the repository root. Exit `0` on pass or skip, exit `4` with structured stderr findings on fail.

This is a canonical per-commit check under `livespec_dev_tooling/checks/`. Once a consumer's library pin reaches the release that ships this module, that consumer's `check-aggregate-completeness` and the fleet-conformance row `canonical-check-slugs-wired` MUST report the slug as unwired until the consumer either wires `check-canonical-origin-owner` or declares a reasoned waiver under §"Shared check inventory" **Canonical-check waivers**.

**Canonical identity.** The canonical `<owner>/<repository>` is read from livespec core's committed fleet manifest, `.livespec-fleet-manifest.jsonc`, as §"Sibling discovery" reads it. `<repository>` is the repository name of the clone's `origin` URL. It MUST be a member of the manifest's `fleet` list or one of its `adopters` entries. `<owner>` is the manifest's top-level `owner` key for a `fleet` member, and that adopter entry's own owner for an adopter. The check MUST NOT introduce a second declaration of a repository's owner. When the manifest cannot be read, or the origin's repository name is not a manifest member, the check MUST emit a structured warning naming why and exit `0`; it MUST NOT guess an owner.

**Where it applies.** The check guards the clones where the expedited incident hook runs, and only those. It MUST emit a structured warning and exit `0`, examining no remote, when any of the following holds:
- git configuration `livespec.sandboxExempt` is `true` (a factory sandbox, which the hook classifies as normal factory follow-up and never judges);
- the environment variable `GITHUB_ACTIONS` is `true` (CI, where `actions/checkout` sets the origin and the hook does not run);
- the `origin` fetch URL does not name host `github.com` (a local path, a `file://` URL or another host, as in test fixtures and mirrors).

Outside those cases the check judges every github.com origin. It MUST NOT skip one because its form is unusual, because a skipped clone the hook later refuses is a false green.

**Accepted forms.** A remote URL is canonical when, after removing one trailing `.git`, it equals `https://github.com/<owner>/<repository>` or `git@github.com:<owner>/<repository>` for the canonical identity, comparing exactly. These are exactly the forms the expedited incident hook accepts. A URL carrying userinfo (for example `https://x-access-token:<token>@github.com/<owner>/<repository>`) is NOT canonical, because the hook compares the URL literally and refuses it. The check MUST redact the userinfo of every URL it reports, and MUST NOT write a credential into `found`, `message` or any log line. The check MUST NOT accept a form the hook refuses (for example an `ssh://` URL, a trailing slash, or a different owner that GitHub redirects to the canonical one), because a check that passes a clone the hook refuses is a false green.

**Algorithm.**

1. Read `git config --get remote.origin.url`. When the clone has no `origin` remote, the check MUST emit a structured warning and exit `0`.
2. Read `git remote get-url --push --all origin`.
3. The check MUST fail when the fetch URL is not canonical. It MUST also fail when the push URLs are not exactly one canonical URL, which covers a wrong push URL and more than one push URL alike.
4. Exit `0` when no finding remains; exit `4` otherwise.

Each finding carries `check_id` `canonical_origin_owner`, `status` `fail`, `remote` (`fetch` or `push`), `found` (the URL read, with userinfo redacted), `expected` (`https://github.com/<owner>/<repository>.git`), and a `message` that MUST contain the exact repair:
- For a fetch finding: `git remote set-url origin https://github.com/<owner>/<repository>.git`.
- For a push finding: `git config --unset-all remote.origin.pushurl`, after which pushes use the fetch URL. This holds however many push URLs the clone carries; `git remote set-url --push` without an old URL rewrites only one of several, so it MUST NOT be the printed repair.

Running every printed command and re-running the check MUST pass.

The check reads local git configuration plus the fleet manifest. It performs no network I/O beyond the manifest read that §"Sibling discovery" performs, and it MUST NOT rewrite any remote itself: repair is the operator's or the managing provisioning path's act.
```

In `SPECIFICATION/scenarios.md`, add:

```
## Scenario: a clone whose origin names a non-canonical owner fails the canonical origin check until repaired

Given a clone of `livespec-ai/livespec-dev-tooling` whose `origin` URL was reset to `https://github.com/thewoolleyman/livespec-dev-tooling.git`
When `python -m livespec_dev_tooling.checks.canonical_origin_owner` runs from the repository root
Then it exits 4 with a finding naming the URL found, the expected URL `https://github.com/livespec-ai/livespec-dev-tooling.git`, and the command `git remote set-url origin https://github.com/livespec-ai/livespec-dev-tooling.git`
And after that command runs, the check exits 0
And a clone whose `origin` is `git@github.com:livespec-ai/livespec-dev-tooling` (with or without `.git`) also exits 0
And a clone carrying two push URLs, `https://github.com/thewoolleyman/livespec-dev-tooling.git` and `https://github.com/livespec-ai/livespec-dev-tooling.git`, fails with a push finding whose repair is `git config --unset-all remote.origin.pushurl`, and passes once that command runs
And a clone whose `origin` is `https://x-access-token:SECRET@github.com/livespec-ai/livespec-dev-tooling.git` fails, and no finding or log line contains `SECRET`
And the same clone with git configuration `livespec.sandboxExempt` set to `true` exits 0 with a warning that the check does not apply
```
