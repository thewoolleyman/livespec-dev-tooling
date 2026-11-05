# Incident host hook entrance

The canonical installed Git hook resolves incident routing before lefthook's
autofix, pairing, prechecks, caches, factory provenance or delegation. Ordinary
invocations retain their existing path. Only an explicit ordinary result (75)
falls through; malformed, unavailable or refused incident requests stop.

Before starting local gates, the hook reads `read-local-gates --receipt-id`
through the same current canonical authority. A retained receipt recovers its
exact original results and exit status without executing gates or appending again.
That includes a failed result and an append whose reply was lost. Current identity
and the exact local tree are checked again before admission. Only an authoritative
absent reply permits initial execution; an unavailable, malformed, conflicting or
stale lookup refuses. Older installed producers that lack this operation refuse
until the canonical lookup capability is released and adopted.

A host repair supplies the shared incident flag, a canonical JSON query in
`LIVESPEC_INCIDENT_AUTHORITY_QUERY`, and a distinct invocation identifier in
`LIVESPEC_INCIDENT_LOCAL_OPERATION`. The query contains `repository`, `item`,
`attempt`, `phase`, `operation`, integer `generation`, and `owner`. These values
select existing authority; they do not create it. The registered orchestrator
reader and credential wrapper authenticate the exact current query. The caller
cannot choose a reader executable. A retained context carrier must agree with
that independently obtained context.

The repair must use a clean feature worktree, match canonical HEAD, remain within
the cumulative original paths and carry a legal Python incident comment in that
changed scope. Commit messages require a nonempty audited `Factory-Override`.
The pre-commit receipt names the exact staged tree separately from HEAD. The
installed hook preserves Git's actual operation-index argument before clearing
Git's environment; partial/path commits and other alternate indexes refuse
rather than certifying a different tree.

Declared fast gates run locally with incident fields removed from children;
slow and unclassified work remains explicitly deferred. A real failure retains
its exit code. Before returning, the hook persists its partial result through
`record-local-gates`, reads current authority again and verifies the local tree
did not change. Receipts never mint normal tokens or factory proof. A conflicting
retry using the same local-operation identifier refuses; retained partial records
remain inspectable on the incident item.

A push reads the carrier state the canonical authority publishes on the current
attempt (`attempt.carrier.state`, one of `branch-reserved`, `head-published` or
`pr-bound`, per the orchestrator's "Carrier identity before and after PR
creation"). Every push requires one exact Git stdin ref update, the approved
local SHA, the actual canonical destination and a single resolved push URL.
A `branch-reserved` or `head-published` carrier admits the first pre-PR push
only to its `target_ref`, with the pushed commit's tree equal to the recorded
`staged_tree`, its parent equal to the recorded `input_parent`, and the remote
precondition confirmed absent (`branch-reserved`) or equal to the recorded
`remote_head` (`head-published`); the forge is not consulted. A `pr-bound`
carrier requires an authenticated open PR whose number, source branch
(the carrier's `target_ref`), base and remote old SHA all match. A commit
changes HEAD, so its old pre-commit authority must be canonically advanced
before push. An attempt that publishes no carrier state, or an unknown state,
refuses by naming the carrier state; a missing PR number is never the reason.

Workflow publication needs separate scoped authority, and emergency inverses
need the independently trusted recovery boundary. Unsupported marker formats
require a legal adjacent Python carrier. Genesis, factory fencing,
focused/manual merge admission, other direct/delegated entrances, CI/templates,
release and installed fleet adoption remain required plan work. Developing this
implementation does not activate either incident flag.
