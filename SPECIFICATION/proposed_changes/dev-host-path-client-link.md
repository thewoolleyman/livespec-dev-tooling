---
topic: dev-host-path-client-link
author: claude-opus-5-5
created_at: 2026-10-23T22:40:19Z
---

## Proposal: The dev-host play points the host PATH Fabro client at a declared client build

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend the section "Dev host Fabro client builds" so the inventory MAY name, through one new key, which declared client build the host PATH Fabro client links to. The dev-host play then makes that PATH client a symbolic link to the named build and refuses any shape that would write a server binary or overwrite a real file. Today nothing in any repository manages the PATH client. The section scopes it out, so moving it is possible only by hand, which this repository's GitOps rules forbid.

### Motivation

Work-item bd-ib-zb2hso (livespec-orchestrator-beads-fabro tenant), step 2, under the fleet capacity coordinator's ruling of 2026-10-23 (option B). On vps the PATH client /home/ubuntu/.local/bin/fabro is a hand-made symbolic link (created 2026-06-30) to /home/ubuntu/.fabro/bin/fabro. That file is the binary both live fabro_server instances on the host start: fabro-server and fabro-server-mi-homelab were both measured enabled and active on 2026-10-23. The PATH client is fabro 0.254.0, which cannot decode gmktec's run board since gmktec holds a kubernetes-sandbox run, so every launcher, watcher and overseer liveness read through it sees gmktec as unobservable. The Petri-era 0.382 client that reads gmktec is already declared in fabro_client_builds and staged by the play. Replacing the shared server file to move the client would have put both servers on the Petri engine at their next restart, so the coordinator ruled that the client must stop sharing a file with a live server. The server instances are being pinned explicitly in a separate inventory change, and the client moves on its own path. That move needs a committed mechanism, which is this proposal.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "Dev host Fabro client builds":

1. In the **Scope.** paragraph, replace the sentence "A factory reached through the host PATH client enters this section only when a repository commits a `bin` for it that names a declared `path`." with: "A factory reached through the host PATH client enters this section only when a repository commits a `bin` for it that names a declared `path`, and the PATH client itself enters it only through `fabro_client_path_client` below." Replace the parenthetical sentence "(On a host where the PATH client is a symbolic link to a server instance's `binary_path`, the exclusion below is what keeps the two roles from writing one file.)" with: "(On a host where the PATH client is a symbolic link to a server instance's `binary_path`, the exclusions below are what keep the two roles from writing one file.)"

2. After the **Documented beside the values.** paragraph, add a new paragraph:

**The PATH client.** The inventory MAY declare `fabro_client_path_client`, and when it does it MUST declare it only in `ansible/inventory/group_vars/dev_hosts.yml`, beside `fabro_client_builds`. It is an object carrying `link`, the absolute path on the dev host of the Fabro client the host PATH resolves, and `target`, which MUST equal the `path` of one `fabro_client_builds` entry. When the key is absent the role MUST NOT create, change or remove anything at any PATH client location.

When the key is present, the role MUST refuse its converge on that host before writing anything on the host for any entry or for `link`, naming the reason, when any of these holds:

- `link` or `target` is missing or not absolute;
- `target` equals no entry's `path`;
- what the host holds AT `link`, read without following a symbolic link, is neither a symbolic link nor absent (so a dangling symbolic link counts as a symbolic link);
- `link` is a symbolic link whose target, after every symbolic link is resolved, is a directory;
- an ancestor of `link` exists on the host and, after symbolic links are resolved, is not a directory;
- `link`, with every symbolic link in its ancestors resolved and its final component left unresolved, equals any entry's `path`, any entry's `<path>.incoming`, or the `binary_path`, explicit or defaulted, of any `fabro_server_instances` mapping declared for that host, each compared after the same resolution;
- anything that is not a symbolic link exists at `<link>.incoming`, read without following; or `<link>.incoming`, resolved the same way, equals any entry's `path`, any entry's `<path>.incoming`, or any such `binary_path`.

A symbolic link that an earlier interrupted converge left at `<link>.incoming` MAY be replaced.

Otherwise the role MUST make `link` a symbolic link whose literal target, as `readlink` prints it, is `target`. It MUST do so only after every declared build is in place, so the PATH client never names a build the converge has not yet installed. The link MUST be owned by the role's owner user and that user's primary group, and every missing ancestor directory of `link` MUST be created as it is for a declared `path`. When `link` is already a symbolic link whose literal target is `target`, the role MUST leave it in place and MUST still ensure its owner and group, so a converge with unchanged inventory on an undrifted host changes nothing. When `link` is absent, or a symbolic link whose literal target is anything else, the role MUST replace it atomically. It does so by creating the new symbolic link at `<link>.incoming` and renaming it onto `link`, so that the symbolic link at `link` itself is replaced; the rename MUST NOT descend into a directory that an existing link at `link` names. The role MUST NOT write through an existing symbolic link at `link`, so the file the old link pointed at is left exactly as found; on vps that file is a live server's binary.

The role's `HOST_VARS.md` MUST document the key, both of its fields and these refusals, and MUST state that moving the PATH client between client families is a change to `target` followed by the play. Its paragraph that today declares the PATH client out of scope, and routes moving it through the `fabro_server` role, MUST be replaced accordingly.

In SPECIFICATION/scenarios.md, add after "## Scenario: the dev-host play stages each pinned Fabro client build and refuses an unsafe entry":

## Scenario: the dev-host play points the PATH client at a declared build and leaves the server binary it used to name untouched

Given a dev host whose inventory declares two `fabro_client_builds` entries and a `fabro_client_path_client` whose `target` is the second entry's `path`

And whose `link` is today a symbolic link to a `fabro_server_instances` mapping's `binary_path`

When the dev-host play converges the host

Then `link` MUST be a symbolic link whose literal target is the second entry's `path`, owned by the role's owner user and that user's primary group

And the file at that `binary_path` MUST hash to what it hashed to before the converge

And a second converge with unchanged inventory MUST change nothing on the host

Given the same host after that converge, with the link at `link` re-owned by another account

When the dev-host play converges the host

Then the converge MUST change only the owner and group of the link at `link`

Given the same host, and an inventory whose `fabro_client_path_client` names a `target` that equals no entry's `path`, or a `link` at which a regular file exists, or a `link` that is a symbolic link to a directory, or a `link` whose leaf is absent and whose parent is a symbolic link to that `binary_path`'s directory, so that it names that `binary_path` once its ancestors are resolved

When the dev-host play converges the host

Then the role's converge on that host MUST refuse, naming the reason, before writing anything on the host

The revise that accepts this proposal MUST, in the same change, add a `tests/heading-coverage.json` entry for the new scenario heading. Its `test` MAY be "TODO", with a non-empty `reason` acknowledging that a real integration-tier test is owed, owned by the implementing work-item filed in the livespec-dev-tooling tenant. The same revise MUST regenerate `tests/heading-coverage-debt.json` mechanically so that it carries the row for that TODO entry.
