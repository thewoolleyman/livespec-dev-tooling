"""The installed capabilities whose serving versions gate incident enablement."""

from __future__ import annotations

__all__: list[str] = ["CAPABILITIES", "SURFACE_CAPABILITY"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
# The contracts.md expedited-incident clause says incident use requires serving-version
# evidence for gate readers, templates, driver hooks, recovery authorization and the
# independent controller. Every audited surface is served by exactly one of them.
CAPABILITIES: tuple[str, ...] = (
    "gate-readers",
    "templates",
    "driver-hooks",
    "recovery-authorization",
    "independent-controller",
)

SURFACE_CAPABILITY: dict[str, str] = {
    "Hook installation and wiring": "driver-hooks",
    "Pre-commit before mode selection": "gate-readers",
    "Commit-msg and TDD": "gate-readers",
    "Pre-push": "gate-readers",
    "Explicit commands and parallel aggregation": "gate-readers",
    "Fast-gate timing": "gate-readers",
    "Focused test selection": "gate-readers",
    "Touched-file coverage": "gate-readers",
    "Full coverage producers/consumers": "gate-readers",
    "Normal evidence caches": "gate-readers",
    "Delegated pre-commit": "gate-readers",
    "Delegated push/replay/explicit gates": "gate-readers",
    "Gate renderer and pod": "templates",
    "Credential/environment boundaries": "driver-hooks",
    "Agent tool and stop guards": "driver-hooks",
    "PR mode transport": "templates",
    "CI matrix/batch/direct action": "templates",
    "CI dependency/aggregate/merge context": "templates",
    "Parity/completeness enforcement": "gate-readers",
    "Spec enforcement and debt": "gate-readers",
    "Workflow-edit authorization": "recovery-authorization",
    "PR factory provenance": "gate-readers",
    "Retrospective bypass audit": "gate-readers",
    "Operator factory routing": "driver-hooks",
    "Incident ownership transfer": "recovery-authorization",
    "Branch/PR resolution": "gate-readers",
    "Acceptance and completion": "gate-readers",
    "Normal master context": "gate-readers",
    "First-failure observer": "independent-controller",
    "Emergency revert and merge authority": "recovery-authorization",
    "Existing reconciler coordination": "independent-controller",
    "Recovery dependency independence": "independent-controller",
    "Failed-run retention": "independent-controller",
    "Late regression/cleanup": "independent-controller",
    "Release and distribution": "templates",
    "Generated projects": "templates",
    "Closure/proof/archive": "gate-readers",
}
