# 004: priority close-out, the word "finished", and naming items

This note amends the charter (note 001) and notes 002 and 003. Where they disagree, this note wins. Each rule below is
also recorded verbatim as a scope event on epic `livespec-dev-tooling-6tgd2z` (2026-11-02) and in
`.ai/coordinator-duties.md` §7 and §9.

## 1. A priority leaves the list only when its plan is completely closed

The maintainer (attended, 2026-11-02 ~06:4xZ), verbatim:

> As for the #1 "Don't Finish" plan, if it is done then you should ensure it is fully archived, close out the session
> tab, and remove it from the list. There's no reason to keep something that is fully archived around in the list.
> Add this to your standing plan workflow but it must be fully archived and its session closed in order to be
> considered completely closed first. And it should be kept around in the main trainer notes as completed until it is
> acknowledged so I know.

The rule:

- A priority's plan is **completely closed** only when both of these hold:
  - its plan is archived: `plan/archive/<slug>/` is on master and its epic is closed;
  - its seat's session has ended and its herdr pane and tab are closed.
- Only then does the coordinator drop the priority from the list. The drop is a `priorities-record` append.
- Until the maintainer acknowledges the drop, every tick report carries this line under `FOR THE MAINTAINER`:
  `COMPLETED: <plan-slug (epic-id)> archived <ref>, seat closed <UTC> — acknowledge to clear`.
- A plan whose children are closed but which still owes its proof, review or archive stays on the list with its true
  status, and its seat stays open.

## 2. "Finished" means completely closed

The maintainer (attended, 2026-11-02), verbatim:

> Okay then your mistake was ever calling Dolt finished when it is not archived and completely wrapped up. That is not
> finished.

What went wrong: from the 05:15Z restart handoff onwards, priority 1, dolt-connection-exhaustion
(dolt-server-tp7tca), was reported as FINISHED because its five carriers had closed. dolt-server-xbilme was still
deferred, and the plan's proof, review and archive were all still owed.

The rule: the words finished, done and complete describe a plan only when it is completely closed (rule 1). Otherwise
the status names what is still owed, for example `carriers closed; awaiting xbilme 7-day window (11-08), then proof,
review, archive`.

## 3. Never a bare item id in anything the maintainer reads

The maintainer (attended, 2026-11-02), verbatim:

> You should never use a bare item ID in a maintainer-facing report item. You must always use the item slug and item
> title so I know what you're talking about.

The rule: name every work item by its title, then its id, for example `beads-web spawns gh api rate_limit once per bead
card every 30 s, costing about 0.3 core on the dev host while a board is open (bd-ib-zm4gpr)`. Name a plan as
`plan-slug (epic-id)`. This applies to asks, status lines, DEPENDENCIES lines and summaries.

## Priorities record in force

The record of 2026-11-02 ~06:4xZ is the current one. The maintainer, verbatim: "Yes make the overseer item priority 1
to replace the Tolt one." Priority 1 is herdr-overseer (overseer-uzvcbn), which must complete "Live Codex pane beside a
sibling Codex in one repo, or in a seat that switched from Claude, reads session-gone" (overseer-5eqavc). dolt left the
list by replacement, not completion. Its plan is not archived, and its parked seat is reopened on 2026-11-09 01:38Z.
