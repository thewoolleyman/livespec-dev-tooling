"""§"Runner-pool cache telemetry" — per-TIER attribution, a deterministic canary, a dead-man column.

"A tier with no emitted signal MUST NOT be considered shipped" is the section's
opening, and the rest of it is a set of shapes the signal has to have. Three of
those shapes are decidable from the committed emitters and each one, when it
breaks, leaves telemetry that still ARRIVES and still looks healthy:

- **One attribute per cacheable operation, "never as a single aggregate that
  hides which tier missed".** A collapsed `cache_hit=true` is not a missing
  signal — it is a present one that answers the wrong question. The pool runs
  several tiers per job; the operational question is always *which* one went
  cold, and an aggregate that averages a served registry with a missing seed
  reads as a partial hit rather than as a broken tier. So the per-job span must
  carry the tier's identity NEXT TO its outcome.

- **A canary that is deterministic, pool-selected, and distinctly tagged.** The
  canary exists so "warm-versus-cold timing for the same repository, phase, host
  and contention is a standing query rather than a remembered benchmark". That
  only works if cold jobs are selected by the POOL, reproducibly, and are
  distinguishable from an operator-set kill switch — otherwise the standing
  query silently mixes deliberate cold canaries with a fleet-wide outage and
  reports the outage as the baseline. Selection by `$RANDOM` would still produce
  the right FRACTION of cold jobs; what it destroys is reproducibility, and no
  span records that it was unreproducible.

- **A dead-man column that is always emitted.** The section requires "a
  dead-man trigger that fires on the ABSENCE of these gauges from the host". A
  trigger that counts a gauge the emitter only sometimes sends cannot
  distinguish a dead host from a quiet one, so exactly one gauge has to be
  unconditional and it has to be the one the trigger counts. The failure here is
  the worst-shaped of the three: a dead-man that cannot fire is indistinguishable
  from a dead-man that has nothing to fire about.

Not asserted here, and deliberately: the trigger-description completeness rule
("Every trigger description MUST name the emitter path, the receiver path, the
owning work item, and a runbook") and the factory-parity clause, whose
forwarded-attribute allowlist is not committed in this tree.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_SPAN_EMITTER = _PHASE2 / "cache-telemetry" / "ci-cache-span.sh"
_HOOK_TEMPLATE = _PHASE2 / "arc" / "hook-pod-template.yaml"
_HOST_GAUGES = _REPO_ROOT / "ci-runner" / "observability" / "ci-cache-gauges.sh"
_DEAD_MAN_TRIGGER = (
    _REPO_ROOT / "ci-runner" / "observability" / "triggers" / "ci-cache-dead-man.json"
)

# The scheme namespace the section mandates, so one query shape covers CI and
# factory, and the per-tier pair that keeps an outcome attributable.
_CACHE_NAMESPACE = "build.cache."
_TIER_ATTRIBUTE = "build.cache.tier"
_HIT_ATTRIBUTE = "build.cache.hit"

# The fleet build-telemetry scheme attributes the section requires every cache
# span to carry. `host.name` rides the resource rather than the span.
_SCHEME_ATTRIBUTES = ("build.env", "repo", "git.commit.sha", "git.branch")

# The canary's knob, and the value it writes so a cold job says WHY it is cold.
_CANARY_KNOB = "CI_CACHE_CANARY_N"
_OPERATOR_SWITCH = "CI_CACHE_KILL_SWITCH"
_CANARY_TAG = "canary"

# The one gauge the host emitter always sends, and therefore the only one a
# dead-man can count.
_DEAD_MAN_COLUMN = "kill_switch"

_ATTR = re.compile(r'attr\("(?P<name>[a-z][a-z0-9_.]*)"')
_WARM_COPY_SPAN = re.compile(
    r"def warm_copy_span\((?P<signature>[^)]*)\):\n(?P<body>(?:.*\n)+?)\n\n"
)


def _span_source() -> str:
    """The per-job span emitter's text."""
    return _SPAN_EMITTER.read_text(encoding="utf-8")


def _warm_copy_body() -> str:
    """The body of the per-tier span builder."""
    matched = _WARM_COPY_SPAN.search(_span_source())
    assert matched is not None, (
        f"the emitter must build one span PER TIER; `warm_copy_span` is that builder and "
        f"it must be present in {_SPAN_EMITTER.relative_to(_REPO_ROOT)}"
    )
    return matched.group("body")


def test_every_per_job_cache_outcome_is_attributed_to_its_own_tier() -> None:
    """The hit rides next to the tier's identity, so no tier's miss is averaged away."""
    body = _warm_copy_body()
    emitted = {matched.group("name") for matched in _ATTR.finditer(body)}
    assert {_TIER_ATTRIBUTE, _HIT_ATTRIBUTE} <= emitted, (
        f"the per-tier span must carry BOTH `{_TIER_ATTRIBUTE}` and `{_HIT_ATTRIBUTE}`. "
        f"A hit without a tier is exactly the 'single aggregate that hides which tier "
        f"missed' the section forbids: it arrives, it looks healthy, and it cannot answer "
        f"the only question a cache miss raises; emitted={sorted(emitted)}"
    )
    off_scheme = sorted(
        name
        for name in emitted
        if not name.startswith(_CACHE_NAMESPACE) and name not in _SCHEME_ATTRIBUTES
    )
    assert not off_scheme, (
        f"every cache attribute must sit in the `{_CACHE_NAMESPACE}*` namespace, which is "
        f"what makes ONE query shape cover CI and factory; an attribute outside it is "
        f"data that exists and that the fleet's standing queries do not select; "
        f"off_scheme={off_scheme}"
    )


def test_every_cache_span_carries_the_fleet_build_telemetry_scheme_attributes() -> None:
    """Spans that cannot be grouped by repo, commit and branch are spans nobody can query."""
    common = re.search(r"^common = \[(?P<attrs>.*?)\]$", _span_source(), re.MULTILINE | re.DOTALL)
    assert common is not None, "the emitter must build one `common` attribute set for every span"
    carried = {matched.group("name") for matched in _ATTR.finditer(common.group("attrs"))}
    missing = sorted(set(_SCHEME_ATTRIBUTES) - carried)
    assert not missing, (
        f"the section requires the fleet's build-telemetry scheme attributes on every "
        f"cache span, and they must ride the COMMON set rather than one span kind — a "
        f"span missing them lands in the dataset and is invisible to every query that "
        f"groups by repository or branch; missing={missing} carried={sorted(carried)}"
    )


def test_the_cold_canary_is_deterministic_and_tagged_apart_from_the_operator_switch() -> None:
    """A reproducible cold sample, distinguishable from a fleet-wide kill."""
    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")
    assert f"name: {_CANARY_KNOB}" in template, (
        f"the canary fraction must be a POOL-set knob (`{_CANARY_KNOB}`) in the pod "
        f"template — selected by the pool, not by anything a workflow can influence"
    )
    selection = re.search(
        rf'case "\$\{{{_CANARY_KNOB}:-\}}" in(?P<body>.*?)esac', template, re.DOTALL
    )
    assert selection is not None, (
        f"`{_CANARY_KNOB}` must drive an actual selection in the lifecycle hook — the "
        f"header prose that mentions the canary decides nothing"
    )
    body = selection.group("body")
    assert "$RANDOM" not in body and "shuf" not in body, (
        "the canary must be selected DETERMINISTICALLY. A random draw yields the right "
        "fraction of cold jobs and destroys the property the canary exists for — that "
        "warm-versus-cold for the same repository, phase and host is a standing query — "
        "and nothing in the emitted data records that it was unreproducible"
    )
    assert re.search(rf"switch={_CANARY_TAG}\b", body), (
        f"a canary-selected job must be tagged `{_CANARY_TAG}`, DISTINCTLY from an "
        f"operator-set `{_OPERATOR_SWITCH}`: sharing one value makes the standing query "
        f"mix deliberate cold canaries with a fleet-wide outage and report the outage as "
        f"the baseline; body={body!r}"
    )
    assert re.search(r'\[ -z "\$switch" \]', body), (
        f"the canary may only apply when `{_OPERATOR_SWITCH}` is unset — an operator "
        f"kill must not be relabelled as a canary sample"
    )


def test_the_dead_man_trigger_counts_the_one_gauge_the_host_always_emits() -> None:
    """Absence is only detectable through a column that is never conditionally omitted."""
    gauges = _HOST_GAUGES.read_text(encoding="utf-8")
    emissions = [
        line.strip()
        for line in gauges.splitlines()
        if re.search(rf"\bput {_DEAD_MAN_COLUMN}\b", line)
    ]
    assert emissions, (
        f"the host emitter must emit `{_DEAD_MAN_COLUMN}` — the section's dead-man fires "
        f"on the ABSENCE of the host's gauges, so at least one of them has to be "
        f"unconditional; gauges={_HOST_GAUGES.relative_to(_REPO_ROOT)}"
    )
    trigger = json.loads(_DEAD_MAN_TRIGGER.read_text(encoding="utf-8"))
    columns = {
        str(calculation.get("column", ""))
        for calculation in trigger["query"].get("calculations", [])
    }
    assert any(column.endswith(_DEAD_MAN_COLUMN) for column in columns), (
        f"the dead-man must count exactly the gauge the emitter always sends. Pointed at "
        f"a conditionally-emitted column it cannot tell a dead host from a quiet one, and "
        f"a dead-man that cannot fire looks identical to one with nothing to fire about; "
        f"columns={sorted(columns)}"
    )
    assert trigger["threshold"]["op"] == "<" and trigger["threshold"]["value"] >= 1, (
        f"the dead-man's threshold must fire on TOO FEW datapoints — an absence trigger "
        f"testing any other direction is a value trigger wearing a dead-man's name; "
        f"threshold={trigger['threshold']}"
    )
