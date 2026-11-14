---
topic: gate-resources-lane-capacity-follow-ups
author: claude-opus-5-5 (seat gate-job-resources)
created_at: 2026-11-11T13:35:28Z
---

## Proposal: Lane capacity is compared only when a repository declares gate_cpu or gate_memory

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The Lane capacity sub-bullet of contracts.md §"Delegated pre-push gate" **Declared gate resources** currently binds every gate client, including the many fleet repositories that declare none of the three keys. Its rule "A gate client that cannot read or parse the file MUST refuse in the same way" therefore refuses those repositories' pushes and commits over a file they never asked to be compared against. This proposal scopes the comparison, and its read-or-parse refusal, to a repository that declares gate_cpu or gate_memory, and adds a scenario stating that behaviour.

### Motivation

The v187 doctor LLM phase raised this as its one high finding when the a-consumer-declares-its-gate-job-resources proposal was revised (recorded on plan epic livespec-dev-tooling-ukoeah, 2026-11-11 02:33Z). It must be fixed before C1b (livespec-dev-tooling-yznwz7) implements Lane capacity, because implemented as written the clause would turn any unreadable queue file into a fleet-wide refusal. A repository that declares no gate cpu or memory requests the renderer's default size, and that size is already held within the committed lanes by the **Gate lane headroom** bullet and by the gate unit on the gates-cq ClusterQueue, so comparing it again adds no protection.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", **Declared gate resources**, *Lane capacity*, replace the opening sentence "The gate client MUST also refuse when no single flavor of the `gates-cq` ClusterQueue has both a nominal CPU quota of at least the Job's CPU request and a nominal memory quota of at least its memory request." with: "When the repository declares `gate_cpu`, `gate_memory` or both, the gate client MUST also refuse when no single flavor of the `gates-cq` ClusterQueue has both a nominal CPU quota of at least the Job's CPU request and a nominal memory quota of at least its memory request. A repository that declares neither key MUST NOT be compared: its full-size Jobs request the renderer's default, which **Gate lane headroom** keeps admissible, and the gate client MUST NOT read the queue file for it."

In the same sub-bullet, replace "A gate client that cannot read or parse the file MUST refuse in the same way, naming the file." with: "A gate client comparing a declaration that cannot read or parse the file MUST refuse in the same way, naming the file. A repository that declares neither `gate_cpu` nor `gate_memory` MUST NOT be refused because the file is absent, unreadable or unparseable." A declaration of `gate_parallelism` alone does not trigger the comparison, because it requests no cpu or memory.

In SPECIFICATION/scenarios.md, after "## Scenario: a declared gate resource that no single gate lane can admit is refused naming the largest lane's quotas", add:

```markdown
## Scenario: a repository that declares no gate cpu or memory is not refused over an unreadable gates queue file

Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and declares neither `gate_cpu` nor `gate_memory`

And the `cluster-queue-gates.yaml` the gate client would read is absent or cannot be parsed

When a push in that repository reaches the gate client on a host eligible under **Host eligibility**

Then the gate client MUST NOT refuse the push because of that file

And it MUST submit the pre-push gate Job at the renderer's default size
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` row for the new scenario heading, owned by livespec-dev-tooling-yznwz7.

## Proposal: The installed gate client parses the gates queue file with a YAML parser the wheel vendors

### Target specification files

- SPECIFICATION/contracts.md

### Summary

*Lane capacity* requires the gate client to read `cluster-queue-gates.yaml` from its in-tree copy or the copy packaged with `livespec_dev_tooling`, but the installed wheel cannot parse YAML. Its runtime dependencies are only anyio and typing-extensions, and its `_vendor/` tree carries jsoncomment, livespec_runtime_budget, returns, structlog and tomli. This proposal requires the wheel to vendor the YAML parser the comparison uses, the way it vendors its other third-party libraries.

### Motivation

The second half of the v187 doctor high finding ("the wheel has no YAML parser"), verified on 2026-11-11 against this repository's pyproject.toml `[project].dependencies` and `livespec_dev_tooling/_vendor/`. A consumer that installs the wheel and declares `gate_cpu` would hit an import failure, or a refusal naming a file that is present but that the client cannot parse, on every gated push. The same thing would happen in every fleet repository, since none of them can be assumed to provide a YAML library.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", **Declared gate resources**, *Lane capacity*, after "The wheel MUST package that file beside its packaged renderer." add: "The gate client MUST parse that file with a YAML parser that `livespec_dev_tooling` itself carries, vendored under `livespec_dev_tooling/_vendor/` as its other third-party libraries are. It MUST NOT depend on a YAML library that the consuming environment happens to provide, and the wheel's declared runtime dependencies MUST NOT be widened to supply one. A parser that the installed client cannot import is a client that cannot parse the file, and refuses under the preceding sentence only when it is comparing a declaration."

## Proposal: The lane-capacity scenario derives its threshold from the committed queue file

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

The scenario "a declared gate resource that no single gate lane can admit is refused naming the largest lane's quotas" states its precondition as literal committed values ("the largest lane's quotas are 15 CPU and `24Gi`", with `gate_cpu = 40`). Those values are already false: on 2026-11-11 gates-poweredge-flavor was committed at 30 cpu / 48Gi (livespec-dev-tooling#4139). A test written to the scenario must therefore either pin a committed value or use a fixture that the scenario does not describe. This proposal restates the Given and Then as a derivation from the committed file.

### Motivation

§"Tests never pin committed configuration values" forbids a test from asserting a literal committed quota. The scenario's 15 CPU / 24Gi was the gmktec lane, and it stopped being the largest lane when the PowerEdge lane rose to 20 cpu and then to 30 cpu. C1b (livespec-dev-tooling-yznwz7) owns the scenario's test and needs a Given that stays true as quotas move.

### Proposed Changes

In SPECIFICATION/scenarios.md, under "## Scenario: a declared gate resource that no single gate lane can admit is refused naming the largest lane's quotas", replace the body with:

```markdown
Given a consuming repository whose `[tool.livespec_dev_tooling]` table sets `delegated_gate = true` and declares `gate_cpu` one more than the largest nominal CPU quota of any flavor committed in `cluster-queue-gates.yaml`

When a push in that repository reaches the gate client on a host eligible under **Host eligibility**

Then the gate client MUST refuse before it submits any gate Job

And its message MUST name the key `gate_cpu`, the declared value, and the largest lane's name and CPU and memory quotas as committed
```

The heading MUST stay unchanged. A test of this scenario MUST read the threshold from the committed file and MUST NOT state it as a literal.

## Proposal: The refusal names one largest lane, chosen by a stated rule

### Target specification files

- SPECIFICATION/contracts.md

### Summary

*Lane capacity* says the refusal MUST name "the CPU and memory quotas of the largest lane", but it never says which lane is largest when the lane with the most CPU and the lane with the most memory differ. Two compliant clients could then name different lanes for the same refusal. This proposal fixes the rule: the largest lane is the flavor with the greatest nominal CPU quota, a tie is broken by the greater nominal memory quota and then by its order in the committed file, and the refusal names that flavor along with its quotas.

### Motivation

The flavor quotas are no longer in proportion. On 2026-11-11 gates-poweredge-flavor stood at 30 cpu / 48Gi beside gates-flavor at 15 cpu / 24Gi, and a later lane may lead on one resource only. The scenario's Then requires the message to name the largest lane's quotas, so the rule has to be exact before C1b (livespec-dev-tooling-yznwz7) writes its assertion.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", **Declared gate resources**, *Lane capacity*, replace "The refusal MUST name the declared key or keys, their values, and the CPU and memory quotas of the largest lane." with: "The refusal MUST name the declared key or keys, their values, and the name and the CPU and memory quotas of the largest lane. The largest lane is the compared flavor with the greatest nominal CPU quota. A tie MUST be broken by the greater nominal memory quota, and then by the flavor that comes first in `cluster-queue-gates.yaml`."

## Proposal: The Declared gate resources spec-first note names what has shipped and who owns the rest

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The *Spec-first* sub-bullet of **Declared gate resources** still says "As of filing, no caller passes `--cpu`, `--memory` or `--parallelism`, so every gate Job in the fleet requests CPU 5, memory `6Gi` and 4 workers." That stopped being true when C1 merged. This proposal replaces it with a note naming the work item that delivered the Keys, Passing, Validation and refusal-kind rules, and the work item that still owns Lane capacity.

### Motivation

C1 (livespec-dev-tooling-c3nd2h) merged as livespec-dev-tooling#4148 on 2026-11-11, and its rendered-Job proof as livespec-dev-tooling#4157. A spec-first note that reads as unimplemented after the code has shipped misleads the next reader and the next revise about what is still owed.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated pre-push gate", **Declared gate resources**, replace the *Spec-first* sub-bullet with: "*Spec-first.* The *Keys*, *Passing* and *Validation* sub-bullets and *A refusal is not an absent verdict* are implemented by livespec-dev-tooling-c3nd2h (livespec-dev-tooling#4148). *Lane capacity* remains spec-first, and work item livespec-dev-tooling-yznwz7 owns it. A revise that ratifies Lane capacity's implementation MUST update this note."
