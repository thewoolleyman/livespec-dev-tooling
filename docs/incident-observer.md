# Independent incident observer

`incident_observer_endpoint.observer_endpoint` is a WSGI callback for individual
GitHub `workflow_job` completion events. It verifies the HMAC of the raw request
before reading the controller store. An authenticated first failing required leaf
can call recovery while the original workflow and its other jobs remain running.
It does not call a workflow-completion API, cancel CI, rerun jobs, classify the
failure or wait for a green revert PR.

The endpoint cannot register an incident from a request, label or environment
variable. The independent host first calls `admit_observer` with the exact
canonical current-authority reader adapter and its separately provisioned
released-controller allowlist. Admission records the incident generation,
operation, owner, original receipt bytes, exact master SHA/run and complete
required-leaf universe. The controller revision must differ from the candidate
revision. A historical receipt cannot authorize admission.

The controller's directory must live outside candidate checkouts, the tenant,
credential projection, factory and gates namespaces. The controller secret and
recovery principal must also be independently provisioned. Its private files are
cached immutable authority and effect receipts, not another lifecycle ledger.
They do not derive authorization by parsing arbitrary JSON supplied by an operator
or request.

Every repository mutation shares one OS-backed lock. An immutable recovery intent
is fsynced before the effect, and its registered generation is checked again
immediately before recovery. Duplicate delivery of another failing leaf shares
the same action id. An unknown outcome remains pending across process restarts;
it cannot issue another effect or admit a replacement generation. The recovery
adapter must use that exact action id for the forge effect and its lookup.

`reconcile_action_receipt` reads the exact external effect receipt after a timeout
and publishes it with the original authority bytes when the canonical tenant
returns. A newer registration never rebinds an older action's receipt to a newer
attempt. A completed reconciliation is retained to avoid duplicate publication.
Corrupt or inaccessible controller state fails rather than selecting normal mode
or starting with an empty fence.

The ordinary reconciler must call `route_ordinary_action` before its existing
rerun, classification or fix-forward action. For the registered incident SHA/run
the independent controller owns the action. Other ordinary runs execute their
existing policy under the same repository lock.

This source slice supplies controlled callback and action adapters. It does not
activate a production observer. Activation and child closure still require:

- The released canonical `incident_authority.py read-current` adapter, including
  exact repository/item/attempt/phase/operation/generation/owner validation and an
  immutable receipt. Its schema-1 `result.attempt` is encoded as sorted compact
  JSON to obtain the exact authority bytes; `authorizes_current_effects` must be
  true, and history results cannot admit. The registered master SHA must occur
  in the authorized landed commit set. This reader's smallest current schema
  does not select CI run ids: the independent released controller must also
  verify exact run/SHA association through its authenticated forge boundary.
  Current incident identity alone cannot authorize an arbitrary run. Reader
  unavailability refuses new admission.
- A normally installed independent released controller, GitHub webhook delivery,
  protected directory, host authentication and narrow recovery capability.
- Wiring the ordinary reconciler to the shared action lock and wiring canonical
  correction/ownership transitions to advance the controller fence **before** any
  new attempt can perform effects. A pending unknown effect must first be
  resolved by its exact receipt.
- Released-build rollout and controlled end-to-end proof, including tenant and
  credential-wrapper outages. Local fixture authority is not live authorization,
  a factory record or proof of installed fleet behavior.
