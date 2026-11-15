---
topic: delegated-pre-push-logs-each-host-authority-member
author: claude-opus-5-5
created_at: 2026-11-15T02:47:16Z
---

## Proposal: A delegated pre-push prints one line for each authority member it runs on the pushing host, pass or fail

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In contracts.md §"Delegated pre-push gate", the **What the delegated gate runs.** bullet already places authorization-reading members on the pushing host and requires a FAILING member to refuse the push with a line naming the member and that it ran on the pushing host. It says nothing about a PASSING member, so a host-side pass prints nothing. This proposal requires the pre-push gate to print, for every such member it runs, one line naming the member, that it ran on the pushing host, the tree hash it judged, and whether it passed. It adds the matching Then line to the existing scenario "an authority-reading member of an opted-in push runs on the pushing host and joins the delegated verdict". No `## ` heading changes.

### Motivation

livespec-dev-tooling-qqkdjc (child of plan epic livespec-dev-tooling-xowhol). Four delegated pushes from hetzner-xubuntu on 2026-11-15 ~01:24Z, each carrying a `.github/workflows` edit, were measured: livespec-overseer (gate run 20261115T012441Z-1005855, bb90eacd), livespec-orchestrator-git-jsonl (20261115T012442Z-1006909, a3e5bbc), livespec-orchestrator-beads-fabro (20261115T012440Z-1005640, 6c3830e1b) and livespec-console-beads-fabro (20261115T012441Z-1006173, e9f88f0). Each push log shows only the gate Job's skip line for check-no-workflow-edits and no host-side run, and each push completed. The refusal half already exists in `livespec_dev_tooling/_gate_host_authority.py` (released v1.123.0), which runs each authority-declaring member on the pushing host and refuses on a non-zero exit or an unevaluable member. But the runner captures a passing member's output and returns the Job verdict unchanged, so a host-side pass is indistinguishable from no host-side run at all, and a reviewer of a workflow-editing push cannot tell from its log whether the authority guard ran. The factory screen classified the item at spec-change tier because the ratified text does not state this behaviour. The same section already sets the precedent: the **Same-tree delegated pre-commit verdict** bullet requires the gate to print the name of each member it ran.

### Proposed Changes

### contracts.md §"Delegated pre-push gate" — **What the delegated gate runs.**

Immediately after the sentence ending "it never treats an unevaluated authorization as granted.", insert this sentence:

> For every such member it runs, the pre-push gate MUST print one line naming the member, that it ran on the pushing host, the tree hash it judged, and whether it passed, so a delegated push whose host-side members all passed never reads the same as one where none ran.

The rest of the bullet is unchanged. The existing refusal line for a failing or unevaluable member MAY be that member's printed line, provided it carries the four facts above.

### scenarios.md §"Scenario: an authority-reading member of an opted-in push runs on the pushing host and joins the delegated verdict"

After the line "And the push MUST complete only when the gate Job reports a green verdict and that member passes on the pushing host", insert:

> And when that member passes on the pushing host, the pre-push gate MUST print one line naming the member, saying it ran on the pushing host, naming the committed tree hash it judged, and saying it passed

The scenario's heading and its other lines are unchanged, so `tests/heading-coverage.json` is unchanged.
