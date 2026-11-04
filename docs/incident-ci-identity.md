# Protected CI invocation identity

`POST /ci/identity` authenticates one supported GitHub Actions invocation. It
accepts the actual OIDC JWT as `Authorization: Bearer <JWT>` and exactly the six
`ObserverArmQuery` body fields: `repository`, `arm_id`, `pr_number`, `base_sha`,
`head_sha` and `receipt_digest`. Query and control secrets cannot authenticate
this route. The exact retained arm must remain unbound and unrevoked before and
after verification. Crypto and network reads run outside the repository effect
lock so already owed recovery can continue.

A successful response has exactly `schema: 1`, `status: "authenticated"`,
`identity`, `policy_sha256`, and four false fields: `authorizes_current_effects`,
`ci_admission`, `authorizes_merge`, `normal_factory_proof`. The identity contains
the signed repository and stable repository/owner IDs, run ID/attempt, check ID,
actual separately resolved job ID, check suite, caller and reusable workflow
ref/SHA, token times, PR ref and synthetic merge SHA, and exact arm/query fields.
No token, signature, secret or session capability is returned. Responses use
`Cache-Control: no-store`; existing current/admitted consumers reject this shape.
Authentication establishes neither command/artifact execution nor complete CI,
current canonical mode, a session, merge permission or factory proof.

## Optional installation policy

`controller.json` is unchanged. The independently protected release manifest may
add one optional member:

```json
"ci_identity_policy": {
  "path": "/etc/livespec-incident/ci-identity.json",
  "sha256": "<SHA256 of exact policy bytes>"
}
```

The policy file must be private, protected against candidate writes, and contain
exactly the following schema (values below illustrate structure only):

```json
{
  "schema": 1,
  "audience": "urn:independently-provisioned-controller",
  "subject": "repo:owner/repository:pull_request",
  "repository": "owner/repository",
  "repository_id": 123,
  "repository_owner_id": 456,
  "approved_reusable_workflows": [
    {
      "ref": "owner/provider/.github/workflows/protected.yml@ffffffffffffffffffffffffffffffffffffffff",
      "sha": "ffffffffffffffffffffffffffffffffffffffff"
    }
  ],
  "issuer_keys": [{"kid": "<independently pinned issuer key ID>", "n": "<RSA JWK modulus>", "e": "AQAB"}],
  "crypto": {"path": "/usr/bin/openssl", "sha256": "<approved executable SHA256>"}
}
```

These example IDs, revision and fixture keys approve no production workflow.
The mutable `reusable-check-matrix` is not implicitly trusted. Provisioning an
approved isolated immutable reusable workflow and obtaining issuer keys through
an independent trust path remain operator obligations. No request or environment
selects policy, audience, keys, issuer endpoint, workflow revision or executable.

The issuer is fixed to `https://token.actions.githubusercontent.com`, with RS256
and JWT headers. Optional bounded `x5t` metadata is accepted and ignored for key
selection. Token-selected key material, key URLs and critical extensions refuse.
Unknown or rotated `kid` values refuse until normal independent policy
reprovisioning updates its digest in the protected manifest and reloads the
controller. There is no request-triggered discovery or key refresh.

The policy and approved executable are rehashed and their lexical/resolved path
ownership and permissions rechecked at invocation and before returning. OpenSSL
runs with fixed arguments, private temporary inputs, a minimal environment,
configuration overrides disabled, output discarded and a timeout. Python only
encodes the pinned public key as DER. The optional executable is deliberately
absent from mandatory manifest `files`: missing, invalid or tampered policy or
crypto makes identity unavailable while preserving existing controller recovery,
query, control and callback routes. Unknown manifest members still refuse startup.

## Supported forge correlation

Only `pull_request` with `refs/pull/<exact PR>/merge` is supported. Let M be the
signed synthetic merge SHA, H the retained arm head, and B its base. The current
PR must be open/unmerged with exact B/H and test `merge_commit_sha=M`; an
independent Git commit read must show exact ordered parents `[B,H]` for M.
Current REST run, job and check `head_sha` must equal H. Provider shapes using M
there are unsupported rather than guessed.

Independently credentialed budgeted forge reads require both the latest run and
the signed attempt to match, including current attempt, repository IDs, event,
workflow path and suite. Complete bounded attempt-job pagination resolves exactly
one canonical `check_run_url` for the signed check ID. Job and check IDs need not
be equal. The independently fetched check must match the suite, head, ID and
GitHub Actions producer. Empty `pull_requests` arrays are supported; they are
not used to infer association. Final latest-attempt, PR, token lifetime, policy,
crypto and arm checks refuse stale or unavailable observations.

This implementation performs no workflow edit, service activation, secret
projection, account creation, policy provisioning or branch-protection change.
Controlled signed fixtures and process/HTTP checks exercise local behavior;
they are not production token, release/adoption or plan completion evidence.

## Retained CI job attachment and historical outcomes

`POST /ci/attach` takes the same actual OIDC Bearer JWT and exact six-field
query as `/ci/identity`. No request identity dictionary, job locator, query or
control secret can stand in for issuer authentication. A fresh attachment
repeats full protected verification (signature, current policy and crypto,
current PR, latest attempt, job and check) outside the repository effect lock,
then reloads the controller record under the lock and rechecks token lifetime,
policy/crypto integrity and the identical unbound, unrevoked retained arm
before it appends. Only local rehashing runs under the lock.

The attachment is kept in one `ci_job_attachments` subtree of the existing
protected controller record (`schema`, `attachments`, `collections`), written
with the same atomic replacement and directory fsync as every other writer.
Rearm, bind, invalidation and recovery writers update their own fields and
leave the subtree untouched; they never parse it.

- **Slot.** One stable slot per repository ID, run ID, run attempt and signed
  check ID (a domain-separated digest). The same actual job ID may not be
  attached under a different signed check.
- **Binding.** The full stable binding is stored with its domain-separated
  digest: retained incident item, attempt, operation, generation, owner and
  phase; arm ID and canonical receipt digest; PR, base, head and synthetic
  merge; repository and owner IDs; caller and reusable workflow refs and SHAs;
  policy digest; run, attempt, job, check and suite IDs; and the attaching
  controller's release and revision. JWT `iat`/`nbf`/`exp`, the raw JWT, its
  signature and the raw authority receipt are never stored or returned, so a
  refreshed token for the same job maps to the same attachment.
- **Recovery.** If the slot already exists, a freshly signature-verified token
  whose every immutable claim, exact query and current policy digest match gets
  back the original deterministic receipt. Recovery is read-only, so it also
  works after the arm is bound, invalidated or rearmed. It never falls through
  to an append and never reauthorizes a changed arm. A changed policy digest, an
  expired token or any differing claim refuses.

`POST /ci/jobs/collect` (control secret) takes exactly `repository`,
`attachment_id` and a caller-chosen `collection_id`. It reads the RETAINED
attempt endpoint, complete bounded job pages for that attempt, and the
canonical check URL, all through `budgeted_gh`. It does not need the current
PR state, the latest attempt, the original token, the current arm or the current
policy. The forge I/O runs outside the lock. Afterwards the record is reloaded,
the binding digest is rechecked, and one observation is appended.

Each observation records its sequence, time, raw provider job/check status and
conclusion, the snapshot classification and a receipt digest. The statuses are
`pending`, `successful`, `failed`, `skipped`, `cancelled`, `unavailable` and
`conflict`. `successful` is recorded only when both the job and the check are
`completed` and both conclude `success`. Neutral, absent, malformed or
unclassified values are `unavailable`. Job and check views that disagree, a
forge identity that contradicts the binding, or a terminal snapshot that
contradicts an earlier terminal observation are all `conflict`. History is
append-only. A late `pending` or `unavailable` observation never replaces
earlier terminal evidence, and no "latest status" summary is exposed. A reused
`collection_id` returns its committed observation, including when two
identical requests race. If the reused ID names a different attachment, the
request refuses. When the attachment table (1024) or an attachment's history
(256) is full, the request refuses and nothing is pruned.

`POST /ci/jobs/inspect` (query secret) returns the attachment receipt and its
complete observation history. Query credentials cannot attach or collect.
Every reply is `no-store` and carries the same four false authority fields.
Existing current and admitted consumers reject these shapes. An independently
observed job success does not prove which commands ran. It grants no admission,
session, merge or factory authority.
