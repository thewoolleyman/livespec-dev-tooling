---
topic: dev-host-fabro-client-builds
author: claude-opus-5-5:fabro-currency
created_at: 2026-10-23T14:36:01Z
---

## Proposal: Dev hosts carry pinned Fabro client builds staged by the dev-host play

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add an obligation that every Fabro client build a committed dispatcher.factories.<name>.bin in this repository names is staged at a declared stable path by a role the dev-host play includes, from a separate control-node source verified against a declared sha256, never by hand, and never at a path the fabro_server role owns.

### Motivation

Dispatchers on vps reach two factories that need two incompatible Fabro client families. The legacy factory (hp, a 0.254 fork engine) is reached through the host PATH client, /home/ubuntu/.local/bin/fabro, a symlink to ~/.fabro/bin/fabro, which is fabro 0.254.0 8869e88. That file is also the fabro_server role's default binary_path. The petri factory (gmktec, a Petri-era engine) is reached through every fleet repository's committed dispatcher.factories.petri.bin, ~/.local/state/fabro-currency/carrier-petri-v0.382-adeefec4c/fabro, and that file was staged by hand. Since the Kubernetes canary of 2026-10-23, gmktec holds a run with a kubernetes sandbox that the 0.254 client cannot decode, so every PATH-client reader of gmktec is blind. The PATH client cannot move to the petri family until the legacy factory pins its own bin, because the R668 rollback to hp stays usable through the bd-ib-iud52v soak to 2026-10-28T17:31Z (fleet coordinator ruling, 2026-10-23 14:3xZ). A committed bin must name a path that GitOps places, or the fleet's routing rests on a binary nobody can reproduce or audit. No section of this specification covers client binaries on a dev host: Fabro factory host provisioning covers factory hosts and their servers, and Fabro factory registry covers only the registry file. Work-items livespec-dev-tooling-lirki2 and bd-ib-zb2hso.

### Proposed Changes

1. In SPECIFICATION/non-functional-requirements.md, insert a new H2 section immediately before "## Dev host disk retention":

## Dev host Fabro client builds

**Scope.** This section states how this repository places, on each host the `ansible/dev-host.yml` play selects through `dev_hosts`, the Fabro CLIENT builds that a Dispatcher running natively there invokes through a committed `dispatcher.factories.<name>.bin`. The host PATH client is out of scope until the factory that uses it commits its own `bin`. It does not govern a Fabro SERVER binary, which §"Fabro factory host provisioning" governs through the `fabro_server` role. (On a host where the PATH client is a symbolic link to a server instance's `binary_path`, the exclusion below is what keeps the two roles from writing one file.) On `vps` the dev host is also the Ansible control node; the control-node and host wording below stays correct for a dev host that is not.

**Declared once, in the inventory.** The inventory MAY declare `fabro_client_builds`, and when it does it MUST declare it only in `ansible/inventory/group_vars/dev_hosts.yml`: a list of objects, each carrying `path`, the absolute path on the dev host where the build is placed; `source`, an absolute control-node path holding the build an operator has staged; and `sha256`, the build's digest as 64 hexadecimal digits, compared case-insensitively. A declared `path` is written only by the play; the `source` tree is what an operator stages and the play reads.

**Committed bins name a declared path.** Every `dispatcher.factories.<name>.bin` this repository commits in its root `.livespec.jsonc` MUST equal the `path` of one `fabro_client_builds` entry, and this repository's `just check` aggregate MUST assert it as `check-dev-host-fabro-client-bins-declared`. When this repository commits no `bin`, that check MUST report itself as vacuous rather than as a pass. A `bin` that a `fabro_factory_registry` mapping declares, once §"Fabro factory registry" admits that key, MUST likewise equal the `path` of one `fabro_client_builds` entry, and that role's pre-write validation MUST refuse one that does not, naming the factory. The same rule for every other fleet repository's committed `bin` is documented in the role's `HOST_VARS.md`, not enforced here.

**Refused before writing.** The role MUST first validate every `fabro_client_builds` entry, and before it writes anything on the host for any entry it MUST refuse the role's converge on that host, naming each refused entry and the reason, when any entry is one of these:  an entry missing `path`, `source` or `sha256`; a `path` or `source` that is not absolute; a `sha256` that is not 64 hexadecimal digits; a `path` that, with symbolic links in its directory components resolved on the host, equals another entry's `path` resolved the same way; a `path` at which something already exists on the host that is not a regular file, a symbolic link included; a `path` an ancestor of which exists on the host and is not a directory; a `path` that, with symbolic links in its directory components resolved on the host, equals the `binary_path`, explicit or defaulted (the default being the one the `fabro_server` role's defaults state, read from there rather than restated) and likewise resolved on the host, of any `fabro_server_instances` mapping declared for that host; when the dev host is the control node, a `source` that, after symbolic links are resolved, is the same file as its own `path` or as any entry's `path`; and a `source` that is absent or hashes, on the control node, to anything but `sha256`.

**Staged by the dev-host play, never by hand.** A role that `ansible/dev-host.yml` includes MUST install each declared build at its `path` with mode 0755, owned by the user a role variable names and that user's primary group, the variable documented with its default in the role's `HOST_VARS.md`. Every missing ancestor directory of a `path` MUST be created, mode 0755, owned by that same user and group; an existing parent directory is left as found. When the file at `path` already hashes to `sha256` the role MUST leave its contents untouched and MUST still ensure its mode and owner, so a converge with unchanged inventory on an undrifted host changes nothing. When it differs, the role MUST replace it atomically, by writing the new build to `<path>.incoming` in the same directory and renaming it into place, and a converge MAY overwrite or remove a `<path>.incoming` left by an earlier interrupted converge, so a Dispatcher already executing the old build keeps a whole file; the outgoing build is not retained, and a rollback is a change to the entry's `source` and `sha256`. A build at a declared `path` MUST NOT be replaced by a hand copy: changing it is a change to the inventory followed by the play. Apart from a declared entry's own `<path>.incoming`, the role MUST NOT remove a file on the host, so a build at a `path` that the inventory no longer declares stays in place, because a Dispatcher in another fleet repository may still name it in a committed `bin`; the role keeps no record of earlier inventories and does not report such a file.

**Documented beside the values.** The role's `HOST_VARS.md` MUST document `fabro_client_builds`, each key of an entry and the owner variable, and MUST name which committed `bin` values in the fleet are expected to point at each declared `path`. It MUST also state why rollback here is a change to the inventory rather than a retained copy, as the `fabro_server` role keeps.

2. In SPECIFICATION/scenarios.md, add after "## Scenario: a Fabro instance that names its own binary and home renders a unit that runs them":

## Scenario: the dev-host play stages each pinned Fabro client build and refuses an unsafe entry

Given a dev host whose inventory declares two `fabro_client_builds` entries, each with a `path`, a staged control-node `source` and its `sha256`

When the dev-host play converges the host

Then each build MUST be present at its `path`, mode 0755, owned by the user the role's owner variable names and that user's primary group, and MUST hash to its declared `sha256`

And a second converge with unchanged inventory MUST change nothing on the host

Given the same host after that converge, and an inventory in which one entry's `source` now hashes to a digest other than its `sha256`

When the dev-host play converges the host

Then the role's converge on that host MUST refuse, naming that entry

And the file at each entry's `path` MUST still be the build the earlier converge installed

Given the same host, which is also the control node, and an inventory in which two entries' paths resolve to one file on the host, or an entry's `path` is a symbolic link on the host, or an entry's resolved `path` equals a `fabro_server_instances` mapping's resolved `binary_path` on that host, or an entry's `source` resolves to its own `path`

When the dev-host play converges the host

Then the role's converge on that host MUST refuse, naming the entry and the reason, before writing anything on the host

3. In the same revision, add a tests/heading-coverage.json row for each of the two new headings, with test "TODO", work_item "livespec-dev-tooling-lirki2" and the reason "A real test at the integration tier is owed for this heading; livespec-dev-tooling-lirki2 owns it.", and regenerate tests/heading-coverage-debt.json with its generator (livespec_dev_tooling/heading_coverage_debt.py) rather than hand-editing it.
