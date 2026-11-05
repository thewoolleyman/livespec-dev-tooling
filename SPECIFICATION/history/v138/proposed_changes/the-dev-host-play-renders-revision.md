---
proposal: the-dev-host-play-renders.md
decision: modify
revised_at: 2026-11-05T04:45:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Work item livespec-dev-tooling-o5xpdy (execution mirror of bd-ib-rtzhfc, plan bd-ib-nmuyjc) was refused at dispatch on 2026-11-05T03:13Z as spec-change tier, held for this topic; legacy-coordinator-agent routed the ratification here under R301. The petri fleet's run count was bounded by three duplicate values that disagreed 16 against 20 on 2026-11-04, and the maintainer directed the fix. The clause makes the fabro_server_instances max_concurrent_runs the single committed value: the dev-host play renders it per registered factory into a one-line world-readable file the fleet launchers read, and refuses a factory whose instance declares none before any host writes. fabro-factories.json keeps exactly server and an optional docker_host, so the Dispatcher's reading of it is unchanged. No ratified statement conflicts and no design record is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Modifications

Wording only. (1) The proposal's 'The --limit and --tags rule for the registry applies to these files in the same way.' is spelled out as a MUST: a run narrowed by --limit or --tags so that it does not run this rendering on a host MUST leave that host's run-cap files unchanged. (2) The sentence 'These are the same emptiness rules the Dispatcher applies when it reads the file.' is reworded to 'The emptiness rules for the registry's own fields are the same ones the Dispatcher applies when it reads the file.' so it does not read as covering the new max_concurrent_runs refusal, which the Dispatcher does not apply. (3) The scenario's second When adds 'and the fabro_server role converges that instance', because settings.toml is rendered by that role on the factory's host, not by the dev-host rendering. No rule was added or dropped.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T04:44:20Z
verdict: NO BLOCKERS
proposal_stem: the-dev-host-play-renders
content_digest: 6923b2cd3e0dff51012b6b465eb583fd6e00f8b59812a21aa201e7ce10581117
