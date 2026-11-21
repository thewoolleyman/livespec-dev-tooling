## The maintainer's statement of what done means

This blockage was completely unacceptable … There needs to be a clear escape valve or else we just delete the hook altogether. I'm leaning towards the latter. [maintainer, 2026-11-21 ~00:2xZ, recorded verbatim on livespec-dev-tooling-osyzv6 retro EGREGIOUS FAILURE 1 and the priorities-record scope event on livespec-dev-tooling-6tgd2z]

## Definition of Done assertions derived from that statement

- No agent session can ever be deadlocked by the fleet_host_guard hook: for any by-hand host change the committed route cannot perform, a session has a documented path that lets the change proceed without a maintainer answer.
- The escape valve is audited: before running a guarded command the session records the exact command and the reason on the ledger, and the hook refuses an invocation that carries no such record.
- A committed backfill PR for every escape-valve use is owed the same day, and a check or report surfaces any use whose backfill is overdue.
- The stale-checkout bootstrap class (a host checkout behind master, a runner start, a host-list edit that the committed route itself needs first) is allowed outright by the hook with no ledger record.
- The change ships fleet-wide through the livespec-driver-claude plugin, and a session on another host observes the valve working after the normal plugin update; if the valve cannot ship by 2026-11-21T12:30Z the hook is deleted instead.

# Charter: fleet-host-guard-escape-valve

Follow-up plan to gitops-deployment-discipline (livespec-qurhq2). Maintainer priority 1, deadline 2026-11-21T12:30Z.

Problem: fleet_host_guard (livespec-driver-claude 2f4c821) refuses every by-hand host change with no escape valve; when the committed route needs the broken thing fixed first, every session deadlocks (retro EGREGIOUS FAILURE 1 on livespec-dev-tooling-osyzv6).

Direction (coordinator recommendation, approved by the maintainer at ~00:1xZ on livespec-dev-tooling-6tgd2z): an audited escape valve; delete the hook if it cannot ship by the deadline.

The assertions were derived by the session from the maintainer's words and are session-derived, not maintainer-confirmed.
