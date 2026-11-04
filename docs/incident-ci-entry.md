# Incident CI entrance

`python -m livespec_dev_tooling.incident_ci_process` exposes `plan`, `run` and
`aggregate`. A run names members with repeated `--target check-name` arguments;
it accepts no caller command or inventory path. The `--repo`, `--report` and
`--reports` paths are supplied by the trusted workflow entrance. The packaged
inventory contains the full existing normal workflow's 71 members, their batches
and the coverage producer/consumer dependency. Its byte digest and source workflow
digest travel with the code. Regenerate it with
`incident_ci_inventory.render_inventory(workflow=...)` and update its module's
digest in the same normally validated release. Only the two already measured fast
checks, lint and format, are classified fast in this increment.

The workflow must install and invoke an independently approved release before it
executes candidate code. A digest embedded in source binds its inventory to that
source; it is not release attestation or protection against candidate-modified
controller code. This increment does not install that workflow entrance.

A current authenticated PR read determines labels, PR number, repository, base
and exact head. An incident PR contains one body block:

```text
<!-- livespec-incident-ci
{"schema":1,"arm":{...},"observer_arm_id":"<arm SHA256>"}
-->
```

The root keys are exact. The existing canonical observer-arm codec validates the
arm; its id must equal SHA256 over `json.dumps(arm, sort_keys=True)` with the
arm's authority receipt encoded as hex. This consistency packet is not authority.
No producer for this new packet is claimed by this increment.

The trusted workflow supplies `LIVESPEC_INCIDENT_OBSERVER_URL` and the read-only
`LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN`. Hosted CI receives neither a tenant
credential nor the arm/bind credential. HTTPS uses system certificate validation
and never follows redirects. Both `/current` and `/admitted` must answer HTTP202
with exact keys `schema`, `status`, `query`; schema is integer1, status is the
route name and query echoes all six exact fields: `repository`, `arm_id`,
`pr_number`, `base_sha`, `head_sha`, `receipt_digest`. The endpoints have distinct
obligations: `/current` reads fresh canonical generation; `/admitted` checks the
retained protected premerge arm. Older servers, missing capabilities, stale
generations and failed reads refuse. These controller capabilities must ship
before this entrance can admit an actual incident.

The executor rechecks both reads before every real member and again when
publishing the aggregate. It compares the complete freshly derived plan,
including selected members and environment, before execution; a retained scope
digest does not authorize edits to a constructed plan. Children receive neither incident flags/context nor
observer credentials. Omitted members remain explicit deferrals. Exact selected
outcomes bind member name, head and plan scope; duplicate, foreign, stale or
unknown outcomes refuse. Missing, failed, cancelled, skipped or timed-out selected
work cannot satisfy the aggregate. Existing outcome files are append-only; a retry
must use a separate workflow-owned report location, since duplicate evidence
refuses instead of silently replacing history.

Outcome files express consistency, not forge authentication. The eventual trusted
workflow aggregate must also enforce actual job conclusions, artifact identities
and its declared dependency graph. Candidate-writable reports alone cannot prove
successful execution. That workflow integration and its protected execution
boundary remain owed; this source helper does not replace GitHub's required jobs.

A master push chooses the entire normal graph and strips both flags and the
context before incident payload or network reads. Ordinary PRs follow the same
complete policy. No workflow, Action, template, branch protection or production
credential changes are included here. Actual workflow wiring, scoped approval
for reduced incident checks, canonical packet publication, independently released
controller/query endpoints, installed adoption and normal factory proof remain on
the existing plan.
