# Independent controller process

Run the normally released installation with its fixed isolated interpreter:

```text
/opt/livespec-incident/venv/bin/python -I -m livespec_dev_tooling.incident_observer_service --config /etc/livespec-incident/controller.json
```

The packaged `data/incident-observer.service` is a provisioning template, not an
activated service. Provision a dedicated controller account distinct from every
candidate and factory account. That account may own its protected configuration,
manifest and state; root ownership is also accepted. No group or other account
may write a file or any lexical/resolved parent. Symlink ownership is checked
separately from target ownership. Root-owned sticky temporary ancestors are
allowed, but a candidate-owned symlink there is refused. The private state
directory must already exist with mode 0700 and must be outside the independent
reference Git clone. The loaded controller package must also be outside that
clone. Startup never creates missing state or falls back to a candidate tree.

`controller.json` has exactly these keys, whose values are independently
provisioned host facts:

```json
{
  "manifest": "/etc/livespec-incident/released-installation.json",
  "candidate_uid": 1000,
  "repository": "owner/repository",
  "repo": "/var/lib/livespec-incident/reference",
  "state": "/var/lib/livespec-incident/receipts",
  "webhook_secret": "/etc/livespec-incident/webhook-secret",
  "control_secret": "/etc/livespec-incident/control-secret",
  "query_secret": "/etc/livespec-incident/query-secret",
  "port": 8765
}
```

Both configuration files and the three distinct secret files require mode 0600 or
stricter. Secrets must each contain at least 32 bytes. The query secret is separate from
both control and webhook secrets. Only its read-only credential reaches hosted
CI; it cannot arm or bind an incident. This change creates no
account, secret, principal, webhook subscription or branch-protection exemption.
The account id above is an example; it must name the real candidate account and
must differ from the serving controller's effective uid.

The protected released-installation manifest has exactly `release`, `revision`,
`package_sha256`, `reader`, `reader_release`, `principal`, `files` and
`required_jobs`, with the optional protected `ci_identity_policy` descriptor described
in [Protected CI invocation identity](incident-ci-identity.md). The provisioner must attest the normally released tag, its exact
Git revision and the installed artifact fingerprint before enabling the service.
`release` must also equal `v` plus the installed distribution version. A source
hash alone does not authenticate a release. `revision` is the approved forty
character Git SHA. `package_sha256` fingerprints every installed package `.py`
path and its contents, including vendored dependencies. Startup also checks every
already loaded dependency's path and every lexical/resolved executable parent.
The serving interpreter's resolved binary must appear in `files`; `files` maps
each absolute executable/script path to its approved SHA256. `reader` and
`principal` are fixed argv lists composed of those authenticated absolute files
plus optional `-I` and `--` separators. The existing `with-livespec-env.sh`
sudo wrapper is explicitly refused: this unit keeps `NoNewPrivileges=true`, so
new admission requires a separately provisioned credentialed canonical-reader
service/client or a reader using credential projection within its own account.
No sudo escalation or weakening of service confinement is supported. No request or incident environment supplies
them. Provision Python readers with `-I`; the unit clears inherited Python/Git
injection variables and uses a fixed PATH and independent working directory.

The reader is the installed canonical `incident_authority.py read-current`
entry point. Its own normal credential provisioning is required for new arms. The canonical
reader service/client and its credential projection remain an installation
prerequisite; the controller does not create credentials or invent a second
reader/authority store. Failure to read canonical current authority refuses new
arm admission. An already retained arm and its recovery receipts remain usable
without that reader or the tenant wrapper.
The principal is the separately provisioned `ProcessInverseForge` process
protocol. Startup requires the normally installed `incident_inverse` and
`incident_inverse_service` modules and uses their `observer_inverse_callback`.
That callback executes within the observer's already held repository lock. No
second inverse implementation or capability is supplied here. When those
installed modules or protected settings are absent, startup exits 2 before
binding a socket. Consumer release-recovery reconciliation runs after that
callback and after the lock is released; it is not recursively invoked here.

The listener binds loopback behind the host's authenticated TLS/reverse proxy.
Independent request threads and bounded request reads prevent an unavailable
tenant reader in `/arm` from serializing the signed first-failure callback.
The existing repository lock continues to serialize actual durable effects.

- `POST /arm` requires `Authorization: Bearer <control-secret>` and an exact
  `ObserverArm` request without controller release/revision or required jobs.
  Those fields come from the host manifest. The canonical current reader must
  verify every identity and the exact receipt bytes before the arm is stored.
  `authority_receipt` uses the existing protected-store hexadecimal encoding;
  `expected_arm_id` is the optional existing compare-and-swap id.
- `POST /admitted` requires the read-only query credential and exact six
  `ObserverArmQuery` fields to read the protected pre-merge arm.
- `POST /current` uses the same query credential and exact query. It performs a
  fresh installed canonical-reader call against the retained arm outside the
  repository lock, then rechecks the unchanged unbound arm under that lock. An
  unavailable reader, stale generation or changed/bound arm refuses. Both query
  replies use schema 1, echo the exact query and disallow HTTP caching. A reply
  observes current authority at that call; consumers recheck each admission
  entrance instead of treating a prior reply as a durable mutation grant.
- `POST /bind` accepts only repository, landed `head_sha` and positive `run_id`.
  It copies identity and authority from the retained arm and authenticates the
  exact merged PR and normal master run through `MergedRunVerifier`. It needs
  independently provisioned read-only forge access, not the tenant wrapper.
- `POST /invalidate-ci` requires the control credential and the exact retained
  arm's `repository`, `arm_id`, `incident_item_id`, `attempt_id`, `generation`,
  `owner`, `phase`, `pr_number`, `base_sha`, `head_sha`, `receipt_digest` and
  `incident_operation_id`, plus a separate immutable invalidation `operation_id`.
  It verifies canonical current authority outside the repository action lock,
  then rechecks the same unbound arm under that lock before fsyncing revocation
  and its receipt. Queries and same-arm rearming then refuse across restarts.
  A changed host manifest cannot rearm the same generation. A canonical newer
  generation may replace it while retaining every earlier invalidation receipt.
  Exact retries recover the original receipt without another canonical read;
  changed bytes under that operation id refuse. The reply explicitly has
  `authorizes_current_effects: false`, including when recovered after replacement.
  The query credential cannot call this route.
  Revocation concerns CI and new merge admission: it preserves the retained
  grant's exact authenticated `/bind` fulfillment and subsequent failure
  recovery. A PR can already have merged before its bind arrives, so a local
  unbound bit cannot justify dropping that obligation. Already bound arms
  refuse invalidation. This primitive does not install an all-writer mode epoch,
  change forge labels, authenticate CI jobs or establish a real premerge fence.
  Every mode writer and actual merge authority still need that integration
  before the incident feature can be enabled.
- `POST /recover` requires the control credential and the reopened-chain
  receipt the orchestrator's regression reopen committed: `repository`,
  `incident_item_id`, `attempt_id`, `phase`, `operation_id`, `generation`,
  `owner` and hexadecimal `authority_receipt` of the `reverting` generation.
  It is the route from a related regression seen on another PR or on master to
  the trusted controller, which otherwise reverts only on a failing leaf of the
  registered master run. A phase other than `reverting`, a generation not after
  the registered landed attempt, another incident, or an unbound later arm
  refuses by name before any read. The installed canonical reader must then
  verify the generation as current, the exact receipt bytes, and that the
  attempt's `landed_commits` and `head` are the registered landed attempt's;
  a stale or unavailable chain refuses and records nothing. The route persists
  the registration's action under the repository lock and calls the SAME
  `recover` callback a failing leaf uses, with a `RegressionReopen` cause in
  place of a leaf completion. Its action id is the registration's, so a leaf
  failure and a reopen of one landed attempt share one action and one revert.
  A repeated receipt answers its retained action from protected state without a
  canonical read, including after a restart or during a tenant outage.
- `POST /reconcile` requires the control credential and exactly `repository`,
  the 64-hex `action_id` and a boolean `retry_publish`. It is the operator's way
  out of an unknown recovery outcome: a timed-out principal leaves the action
  `pending`, and a pending action refuses every later `/arm`. The route asks the
  principal's `lookup` for the action's exact receipt, using the intent retained
  in protected state, and on a receipt marks the action `completed` so a later
  `/arm` can proceed. It takes no receipt from the caller. While no receipt is
  available the action stays `pending`, and the reply says so. With `retry_publish:
  true` it then runs that retained intent through the principal under the
  repository lock, past the refusal an unresolved lookup raises, and refuses if the
  current registration is no longer the action's. The principal's own ledger makes
  this safe: it settles any open attempt from forge facts, re-sends the one recorded
  commit when master has not moved, and starts one new attempt only when no earlier
  attempt can have landed. A repeat after completion answers the retained receipt
  with no principal call. A completed action's receipt still has to be recorded in
  the chain with the orchestrator's `record-revert-receipt`.
- `POST /callback` verifies GitHub's raw-body HMAC with the existing verifier,
  requires the configured repository, then uses the existing observer endpoint.
  The first registered failing required leaf records immutable intent and calls
  recovery while other original CI jobs remain running. Duplicate deliveries
  retain the same effect identity.

Local controlled settings, mock reader/principal responses and process/HTTP
checks exercise the serving adapter. They do not prove production account
separation, a released principal's authority, real webhook delivery, installed
fleet adoption or factory acceptance. Normal release, protected installation,
independent deployment and the plan's outage/recovery drills remain required
before incident activation or closure of the observer carrier.
