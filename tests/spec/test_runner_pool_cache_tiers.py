"""§"Runner-pool build cache tiers" — the one committed budget, and the guardrails on its writer.

Most of this section is a posture the pool either has or does not have, and the
isolation suite already tests the trust half from inside a routed job. Two
clauses are different: they are stated as SINGLE-SOURCING and as REFUSAL
obligations, which are properties of the committed files rather than of a
running pool, and both fail without a symptom.

**"stated in exactly one committed place that governs BOTH".** The seeded tree's
per-start cost "MUST be capped by one byte budget and one file budget stated in
exactly one committed place that governs both the populator's refusal and the
node's lifecycle sweep's judgement". The word doing the work is *both*. Two
readers judge the same generation — the populator decides whether to publish it,
the sweep decides whether to report the live one as over budget — and if either
carries its own copy of the numbers, the copies drift and the two readers
disagree about the same tree. Neither errors: the populator publishes happily
against its number while the sweep reports an over-budget finding against its
own, or worse, reports nothing at all. So the assertion is that neither consumer
states a budget of its own, and both name the same ConfigMap.

**A refusal that keeps the previous generation.** "the populator MUST refuse to
publish a generation over either budget, LEAVING THE PREVIOUS GENERATION LIVE".
A refusal that unpublished the current tree would convert a size regression into
a pool-wide cold-cache event — every job cold, no error anywhere, just slower.
So the refusal path has to move the new generation aside rather than replace the
live one, and the budget has to FAIL CLOSED when it is absent: a populator that
defaulted a missing budget to some number would publish an unbounded generation
the first time the ConfigMap failed to mount.

**Populator guardrails.** "the populator MUST be capped in CPU parallelism,
scheduled at a lower CPU and I/O priority than jobs, and MUST NOT start a build
while the pool's admitted-job count is above a configured threshold." The
populator's builds run on the node the jobs use, so each of these is the
difference between a background refresh and a self-inflicted contention event on
the gating pool — and a dropped `nice` is invisible in every artifact except job
duration.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WARM_CACHE_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache"
_CRONJOB = _WARM_CACHE_DIR / "warm-cache-cronjob.yaml"
_POPULATOR = _WARM_CACHE_DIR / "warm-cache-populate.sh"
_SWEEP = (
    _REPO_ROOT
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "runner-pod-lifecycle"
    / "scan-runner-pod-lifecycle.sh"
)

# The one committed place, and the two budget axes it states.
_BUDGET_CONFIGMAP = "warm-cache-budget"
_BUDGET_NAMESPACE = "ci-warm-cache"
_BUDGET_KEYS = ("bytes", "files")

# The populator's environment names for the two axes.
_BUDGET_VARIABLES = ("WARM_BUDGET_BYTES", "WARM_BUDGET_FILES")

# Lower CPU and I/O priority than the jobs sharing the node.
_PRIORITY_TOOLS = ("nice", "ionice")
_ADMITTED_JOB_THRESHOLD = "POPULATE_ADMITTED_JOB_THRESHOLD"

_CONFIGMAP_BUDGET = re.compile(
    rf"name:\s*{_BUDGET_CONFIGMAP}\n\s*namespace:\s*{_BUDGET_NAMESPACE}\ndata:\n"
    r"(?P<data>(?:\s+\w+:\s*\"\d+\"\n)+)"
)
_DATA_ENTRY = re.compile(r"^\s+(?P<key>\w+):\s*\"(?P<value>\d+)\"$", re.MULTILINE)
# The live symlink the publish path swings; the refusal path must not name it.
_CURRENT_LINK = "CURRENT_LINK"

# A cargo BUILD at shell-command position. The leading `(?<!")` keeps a build
# command QUOTED into a manifest out of the match — it is a recorded string,
# not an invocation.
_CARGO_BUILD = re.compile(r'(?<!")cargo (?:\+\S+ )?(?:\$\{invocation\}|fuzz build|build\b)')

# Line starts that MENTION a build without running one: a comment, or a
# diagnostic that quotes the command it just ran.
_NON_INVOCATIONS = ("#", "log ", "printf", "echo ")

_KEY_REF = re.compile(
    r"valueFrom:\s*\n\s*configMapKeyRef:\s*\n\s*name:\s*(?P<name>\S+)\s*\n\s*key:\s*(?P<key>\S+)"
)


def _budget_from_configmap() -> dict[str, int]:
    """The two budget numbers as the one committed ConfigMap states them."""
    matched = _CONFIGMAP_BUDGET.search(_CRONJOB.read_text(encoding="utf-8"))
    assert matched is not None, (
        f"the byte and file budgets must be stated in one committed place — the "
        f"`{_BUDGET_NAMESPACE}/{_BUDGET_CONFIGMAP}` ConfigMap; "
        f"file={_CRONJOB.relative_to(_REPO_ROOT)}"
    )
    return {
        entry.group("key"): int(entry.group("value"))
        for entry in _DATA_ENTRY.finditer(matched.group("data"))
    }


def _populator_assignments(*, variable: str) -> list[str]:
    """Every line of the populator that assigns one budget variable."""
    return [
        line.strip()
        for line in _POPULATOR.read_text(encoding="utf-8").splitlines()
        if re.match(rf"^{variable}=", line.strip())
    ]


def _over_budget_branch() -> str:
    """The populator's over-budget arm, from its condition to the next arm."""
    source = _POPULATOR.read_text(encoding="utf-8")
    matched = re.search(
        r"^  elif \[ \"\$\{WARM_NEW_BYTES\}|^  elif \[ \"\$\{new_bytes\}\" -gt "
        r"\"\$\{WARM_BUDGET_BYTES\}\".*?\n(?P<body>(?:    .*\n)+)",
        source,
        re.MULTILINE,
    )
    assert matched is not None, (
        "the populator must decide over-budget in its own arm, so that a refusal cannot "
        "share a path with a publish"
    )
    return matched.group("body")


def _cargo_builds() -> list[str]:
    """Every executable line of the populator that runs a cargo BUILD."""
    return [
        line.strip()
        for line in _POPULATOR.read_text(encoding="utf-8").splitlines()
        if line.strip()
        and not line.strip().startswith(_NON_INVOCATIONS)
        and _CARGO_BUILD.search(line)
    ]


def _refuses_on(*, variable: str) -> bool:
    """True when a guard naming `variable` aborts the run within its own statement."""
    lines = _POPULATOR.read_text(encoding="utf-8").splitlines()
    return any(
        variable in line and any("exit 2" in nearby for nearby in lines[index : index + 3])
        for index, line in enumerate(lines)
    )


def test_the_two_budgets_are_stated_once_and_injected_from_that_one_place() -> None:
    """One ConfigMap states both axes; the populator receives them, never restates them."""
    budgets = _budget_from_configmap()
    assert sorted(budgets) == sorted(_BUDGET_KEYS) and all(
        value > 0 for value in budgets.values()
    ), (
        f"the one committed place must state BOTH axes as positive numbers — a seeded "
        f"tree capped on bytes alone still ships unbounded file COUNT, which is the axis "
        f"that costs a job start on any medium; budgets={budgets}"
    )

    cronjob = _CRONJOB.read_text(encoding="utf-8")
    injected = {
        ref.group("key")
        for ref in _KEY_REF.finditer(cronjob)
        if ref.group("name") == _BUDGET_CONFIGMAP
    }
    assert set(_BUDGET_KEYS) <= injected, (
        f"the populator must receive both budgets FROM that ConfigMap; an axis it does "
        f"not receive is an axis it cannot refuse on; injected={sorted(injected)}"
    )

    restating = sorted(
        assignment
        for variable in _BUDGET_VARIABLES
        for assignment in _populator_assignments(variable=variable)
        if re.search(r"\d", assignment)
    )
    assert not restating, (
        f"the populator must not state a budget of its own — not even as a fallback "
        f"default. Two readers judge the same generation (the populator's refusal and "
        f"the sweep's finding); a second copy of a number drifts from the first and the "
        f"two silently disagree about the same tree, one publishing what the other "
        f"reports as over budget; restating={restating}"
    )


def test_the_populator_fails_closed_on_an_absent_budget_and_keeps_the_live_generation() -> None:
    """A missing budget refuses; an over-budget generation is set aside, not swapped in."""
    source = _POPULATOR.read_text(encoding="utf-8")
    for variable in _BUDGET_VARIABLES:
        assert f'{variable}="${{{variable}:-}}"' in source, (
            f"`{variable}` must default to EMPTY, so an unmounted ConfigMap is a refusal "
            f"rather than a number. A numeric fallback publishes an unbounded generation "
            f"the first time the mount fails, and reports success"
        )
        assert _refuses_on(variable=variable), (
            f"`{variable}` must be validated to a positive integer before a generation is "
            f"published, and an unusable value must ABORT the run — the fail-closed "
            f"direction the section requires of invalid configured bounds"
        )
    branch = _over_budget_branch()
    assert re.search(r'mv -T "\$\{new_gen\}" "\$\{new_gen\}\.\w+"', branch), (
        f"the over-budget path must set the NEW generation aside rather than promote or "
        f"delete it; branch={branch!r}"
    )
    assert _CURRENT_LINK not in branch, (
        f"the over-budget path must not touch the live symlink. Unpublishing instead of "
        f"refusing turns a size regression into a pool-wide cold-cache event — every job "
        f"cold, no artifact recording a failure; branch={branch!r}"
    )


def test_the_sweep_judges_against_that_same_one_place() -> None:
    """The second reader names the ConfigMap rather than carrying its own numbers."""
    source = _SWEEP.read_text(encoding="utf-8")
    assert f"{_BUDGET_NAMESPACE}/{_BUDGET_CONFIGMAP}" in source, (
        f"the lifecycle sweep's judgement must resolve to "
        f"`{_BUDGET_NAMESPACE}/{_BUDGET_CONFIGMAP}` — the same committed place the "
        f"populator's refusal reads, which is what 'governs both' means; "
        f"sweep={_SWEEP.relative_to(_REPO_ROOT)}"
    )
    budgets = _budget_from_configmap()
    embedded = sorted(
        f"{number}: {line.strip()}"
        for number, line in enumerate(source.splitlines(), start=1)
        if re.search(r"warm_budget_(bytes|files)=[\"']?\d", line)
        or any(re.search(rf"budget\w*=[\"']?{value}\b", line) for value in budgets.values())
    )
    assert not embedded, (
        f"the sweep must not carry its own copy of either budget: a second literal drifts "
        f"from the ConfigMap the populator refuses against, and the drift presents as a "
        f"sweep that reports nothing rather than as an error; embedded={embedded}"
    )


def test_the_populator_is_deprioritized_and_yields_to_a_busy_pool() -> None:
    """Guardrails on the writer that shares a node with the jobs it exists to speed up."""
    source = _POPULATOR.read_text(encoding="utf-8")
    builds = _cargo_builds()
    assert builds, "the populator must run the Rust builds this guardrail governs"
    unpriced = sorted(
        build
        for build in builds
        if not all(re.search(rf"\b{tool}\b\s+-", build) for tool in _PRIORITY_TOOLS)
    )
    assert not unpriced, (
        f"EVERY one of the populator's builds must run at lower CPU and I/O priority than "
        f"jobs ({' + '.join(_PRIORITY_TOOLS)}) — they run on the node the jobs use, so a "
        f"build without the prefix is a background refresh competing with the gating "
        f"pool, visible in no artifact except job duration; unpriced={unpriced}"
    )
    assert _ADMITTED_JOB_THRESHOLD in source, (
        f"the populator must not START a build while admitted jobs exceed the configured "
        f"threshold; `{_ADMITTED_JOB_THRESHOLD}` is that gate"
    )
    assert _ADMITTED_JOB_THRESHOLD in _CRONJOB.read_text(encoding="utf-8"), (
        f"`{_ADMITTED_JOB_THRESHOLD}` must be CONFIGURED where the populator runs — an "
        f"unset threshold is a gate with nothing to compare against"
    )
