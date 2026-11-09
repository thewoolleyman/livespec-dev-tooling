# Incident CI entrance

`python -m livespec_dev_tooling.incident_ci_process` exposes `plan`, `run` and
`aggregate`. A run names members with repeated `--target check-name` arguments;
it accepts no caller command or inventory path. The `--repo`, `--report` and
`--reports` paths are supplied by the trusted workflow entrance. The packaged
inventory contains the full existing normal workflow's members, their batches,
their timing classes and the coverage producer/consumer dependency. It derives
only from the workflow's contributed check-target set and from each member's
`# incident-timing:` annotation in `check-targets.txt`, never from whole-file
bytes: a ci.yml edit that leaves that set unchanged, such as a runs-on or step
edit, needs no inventory change, while a target added, removed or renamed, or a
timing annotation changed, fails the derivation test naming the difference until
the data file is regenerated with
`incident_ci_inventory.render_inventory(workflow=..., inventory=...)`. No digest
of the workflow or of the inventory travels with the code.

The timing class is read by the same reader the local hooks use
(`incident_gate_inventory.timing_classes`), so one annotation classifies a gate
on both expedited paths (livespec-dev-tooling-oqpw6t). Because the entrance runs
the RELEASED package, a changed annotation reaches CI with the next release. The
coverage and spec prefixes still override the timing class here: they are the
omission policy that lets the normal jobs skip a member, not a timing class.

A member classified `not-applicable` (it encodes a normal-path precondition
an incident commit cannot meet) is deferred with `incident-policy:not-applicable`
and is not omitted: its normal job still runs it.

`run` executes its selected members through the normal aggregate's own runner
(`_check_target_runner`): in parallel, under the same worker cap, with stdin
closed, in the caller's process group, with the normal aggregate's
coverage-namespace isolation and producer/consumer ordering. Each member's
captured output is written to the job log as that member completes. It passes
no deadline, because a selected CI member is required evidence and the
aggregate has no deferral for one cut short; the job's timeout bounds it. The
recheck before each launch is shared: one confirmed `/current` and `/admitted`
read pair serves every launch for 30 seconds, and a single refusal is retried
once before the run refuses.

The workflow must install and invoke an independently approved release before it
executes candidate code. Packaged-data integrity is the installed release's
integrity; the inventory is not release attestation or protection against
candidate-modified controller code. The `incident-ci` job of
`.github/workflows/ci.yml` is that installed workflow entrance, since
livespec-dev-tooling#3524: it resolves the latest release tag from the forge,
installs that released `livespec-dev-tooling` into a virtualenv outside the
workspace, and invokes `plan`, `run` and `aggregate` from that interpreter with
`-I` over the candidate checkout, so the candidate tree's package is never
importable. The candidate's own environment is used only by the `just` members
the released entrance spawns. The job is additive: `ci-green` requires it in
addition to every normal job, never instead of one.

A current authenticated PR read determines labels, PR number, repository, base
and exact head. The job takes the incident path only on a `pull_request` event
whose authenticated body read carries the block's opening line alone on a line;
a body that merely mentions the marker, any other pull request and every push
select nothing and execute no check in this job, so the complete normal graph is
the gate. On the incident path the released plan decides the mode, projected
from the `expedited-incident-response` label. When it selects any mode other
than `expedited-repair`, the retained block is ignored the same way: the job
records a notice, executes no check, leaves its `omitted` output unwritten and
exits 0, so an unexpedited follow-up that kept the block runs the complete
normal policy. A plan refusal still fails the job. An incident PR contains one
body block:

```text
<!-- livespec-incident-ci
{"schema":1,"arm":{...},"observer_arm_id":"<arm SHA256>"}
-->
```

The root keys are exact. The existing canonical observer-arm codec validates the
arm; its id must equal SHA256 over `json.dumps(arm, sort_keys=True)` with the
arm's authority receipt encoded as hex. This consistency packet is not
authority; it is what the `incident-ci` job reads from the pull-request body
before it asks the observer. No command in this repository produces the packet;
it is written into the pull-request body.

The trusted workflow supplies the repository variable
`LIVESPEC_INCIDENT_OBSERVER_URL`, the read-only secret
`LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN` and, since livespec-dev-tooling#3642,
the optional repository variable `LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR`. When
that variable holds an IP literal the client dials it instead of resolving the
URL's host, while keeping the URL's host for SNI, the certificate check and the
`Host` header; an invalid literal refuses, and an unset variable changes
nothing. An incident PR is refused with a named cause when the URL or the token
is missing. CI receives neither a tenant credential nor the arm/bind credential.
HTTPS uses system certificate validation and never follows redirects. Both
`/current` and `/admitted` must answer HTTP202 with exact keys `schema`,
`status`, `query`; schema is integer1, status is the route name and query echoes
all six exact fields: `repository`, `arm_id`, `pr_number`, `base_sha`,
`head_sha`, `receipt_digest`. The endpoints have distinct obligations:
`/current` reads fresh canonical generation; `/admitted` checks the retained
protected premerge arm. Older servers, missing capabilities, stale generations
and failed reads refuse. The observer service in this package
(`incident_observer_service`, deployed by the `incident_observer` Ansible role)
answers both routes.

The executor rechecks both reads before every real member and again when
publishing the aggregate. It compares the complete freshly derived plan,
including selected members and environment, before execution; a retained scope
digest does not authorize edits to a constructed plan. Children receive neither
incident flags/context nor observer credentials. Omitted members remain explicit
deferrals. Exact selected outcomes bind member name, head and plan scope;
duplicate, foreign, stale or unknown outcomes refuse. Missing, failed,
cancelled, skipped or timed-out selected work cannot satisfy the aggregate.
Existing outcome files are append-only; a retry must use a separate
workflow-owned report location, since duplicate evidence refuses instead of
silently replacing history.

Outcome files express consistency, not forge authentication. Candidate-writable
reports alone cannot prove successful execution, and this source helper does not
replace GitHub's required jobs: the aggregate does not itself verify other jobs'
conclusions, artifact identities or the declared dependency graph, and the jobs
`ci-green` requires remain the gate for those. The workflow therefore lets the
aggregate omit work only after it has PASSED: the `incident-ci` job writes its
`omitted` output from the released aggregate's own JSON, naming the members it
deferred for the `incident-policy:coverage` or `incident-policy:spec` reason,
and nothing else writes that output. The jobs holding those members still run on
every event, report a listed member through an explicit
`omitted-by-incident-policy` step instead of running it, and run in full when
`incident-ci` failed or refused. `ci-green` requires the same jobs as on any
other run and repeats the omitted list. The job uploads its outcome records as
the `incident-ci-outcomes` artifact.

A master push chooses the entire normal graph and strips both flags and the
context before incident payload or network reads. Ordinary PRs follow the same
complete policy. Aggregate enforcement of actual job conclusions and artifact
identities, scoped approval for reduced incident checks, canonical packet
publication, installed adoption and normal factory proof remain on the existing
plan.
