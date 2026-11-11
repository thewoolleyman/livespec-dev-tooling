# The incident fleet audit

`just incident-fleet-audit` and `just incident-enable <owner/repo>` implement the closing
paragraph of `SPECIFICATION/contracts.md` §"Expedited incident execution". Work item
`livespec-dev-tooling-3wcldx`, plan `expedited-incident-response-flag`.

## What is read, and from where

Nothing here is steerable by the caller. There is no owner switch; the claims are the file this
code was released with; the consumer clones are the siblings of this code's primary checkout; the
account is the one the account database names for the running uid. No environment variable moves
any of them. The recipes run `uv run --no-sync` so the audit never rewrites the venv it reads.

| Source | Read |
| --- | --- |
| Membership and identity | livespec core's `.livespec-fleet-manifest.jsonc` from core's default branch over the git transport, read twice. The second read must be byte-identical (by digest) to the first, or the manifest is unauthenticated. |
| Claims | `config/incident-fleet-evidence.json`: the operator's statement of disposition, owner, proof and the release build a row expects. A claim never carries serving evidence; a `serving_build` key is refused. |
| Serving version | One reader per capability, below. Each is read twice, independently; a claim counts only when both reads equal its release build. |

A read that cannot be taken is **unverified**: the row is `unclassified`, the consumer is left out
of the ready list and the findings name the consumer and the capability.

## One reader per capability

| Capability | Serving version | Unverified when |
| --- | --- | --- |
| `gate-readers` | the commit `direct_url.json` records for `livespec_dev_tooling` in the consumer's own `.venv` (release-keyed when the consumer runs its own source, below). The consumer's interpreter is never run. | no clone, no `.venv` (for example `openbrain`, `resume`, `homelab` on a host that has none), no or several installs, an install that is not a recorded revision, a tracked modification in an own-source checkout (an untracked file does not count), or a release-keyed reason below |
| `templates` | the one commit that every pin of this library's reusable workflows (`.github/workflows/...@ref`) and composite actions (`.github/actions/...@ref`) names, across ALL of the consumer's default-branch `.github/workflows/*.yml` files, read from one blobless clone (a tag is resolved to its commit); a consumer that runs its own local workflows (this library always, any other consumer with no such pin) is release-keyed against its default-branch commit, below | an unreadable workflow directory or file, pins that disagree, a ref that names no tag or commit, no template use at all (for example `dolt-server`) |
| `driver-hooks` | `plugin=<commit>` for every plugin the consumer's `.claude/settings.json` enables, from the install record whose project path is the consumer's clone, with its plugin cache present | an enabled plugin that is not installed for this project, no cache, an unreadable registry |
| `recovery-authorization` | the controller's serving version plus the single always-bypass GitHub App on the consumer's default-branch ruleset | no verified controller, no or several bypass actors, not an always-bypass Integration |
| `independent-controller` | `v<version>@<commit>` of the venv the RUNNING `livespec-incident-observer.service` main process was started from, and only if the process started after that install | the unit is not `active`/`running`, the process is not the packaged observer command, no single recorded install, the process predates its install, or the repository is not the one the observer serves (`thewoolleyman/livespec-dev-tooling`) |

The controller reader never opens the protected `controller.json` (the operator cannot read it, and
a release name written there is a claim) and never consults the auditor's own package.

## Release-keyed rows: a consumer that serves from its own source

Two reads would otherwise key to the consumer's own commit: the gate readers of a consumer whose
`.venv` is an editable install of its own checkout, and the templates of a consumer that runs its
own local workflows. A claim committed to `config/incident-fleet-evidence.json` can never name the
commit that contains it, so those reads are keyed to a RELEASE
(`livespec_dev_tooling/_incident_fleet_release_keyed.py`):

- The serving build is the newest `vX.Y.Z` tag that is an ancestor of the serving commit (the
  checkout's HEAD, or the default-branch tip read in the consumer's clone on this host). The tag's
  commit must be confirmed on the remote; so must every release a claim names.
- A claim for such a row names a release (for example `v1.193.0`), never a commit. It may name an
  older release than the newest: the claim is judged against the release it names.
- It is judged PER ROW. A row serves the claimed release only while every file of that row's
  surface at the serving commit is byte-identical to that release's. Commits, and later releases,
  that touch only files outside the surface leave the row serving. A surface is the exact file set
  its reader serves from (`livespec_dev_tooling/_incident_fleet_surface_files.py`): the surface's
  roots, pinned by a test, plus the in-package modules they import or run and the local workflows
  and actions they call. It is never the whole tree, because this repository's master moves many
  times an hour and cuts several releases a day.
- Releases are compared newest first, one `git diff --name-only` per release shared by every
  surface of the capability. A surface stops serving at the first release that changed one of its
  files, and every older release is judged changed since it too, naming the files found changed
  there, without another comparison. Comparing stops once no surface still serves.
- An unclassified release-keyed row names its reason in the findings: no release ancestor, a tag
  the remote does not confirm, the surface's changed or absent files, a claim naming a release that
  is not an ancestor of HEAD, a release whose changed files could not be read, or a tracked
  modification.
- The `serving` line prints the newest release, `release vX.Y.Z at HEAD <commit>`; each row that
  classifies through a release claim prints the release its claim named, at that HEAD.

On the dev host (2026-11-10) only `thewoolleyman/livespec-dev-tooling` is read this way, for both
capabilities.

## The ready list and enablement

A consumer is ready when every row is classified, none is `deliberately-normal`, at least one is
`implemented`, and all five capabilities were read. A `not-applicable` row needs a recorded reason,
the manifest identity and a serving version equal to its release build, and never makes a consumer
ready on its own. `just incident-enable` runs its own fresh audit and writes
`~/.local/state/livespec/incident-enabled/<owner>__<repo>.json` only for a ready repository; it
refuses, naming the missing evidence (or the unauthenticated-manifest finding), for any other.

## Not done by this item

- **Committed claims.** `config/incident-fleet-evidence.json` is empty. Authoring the claims for
  15 applicable consumers across 37 surfaces and 2 guidance surfaces for each of 7 instruction-only
  adopters needs per-row proof references read from the installed fleet; it is carried by
  `livespec-dev-tooling-v46q5g`.
  Until then every row prints `unclassified`, the per-capability `serving` lines still print the
  version read for every consumer, and the ready list is empty.
- **Resolver enforcement.** The incident execution resolver does not yet consult the enablement
  record, so `EXPEDITED_INCIDENT_RESPONSE=1` in a repository that was never enabled is not refused
  by it. Where the record lives so that every resolver (dev host, CI runner, controller host) can
  read it is a design decision this item does not make; it is carried by
  `livespec-dev-tooling-2xxnku`.
