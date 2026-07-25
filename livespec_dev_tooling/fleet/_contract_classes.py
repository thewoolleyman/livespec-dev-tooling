"""Fleet repository class partitions for central obligation rows."""

from __future__ import annotations

__all__: list[str] = [
    "ALL_CLASSES",
    "DEV_TOOLING_PIN_CLASSES",
    "PIN_WEB_CLASSES",
    "RECEIVING_SHIM_CLASSES",
    "REPO_CLASSES",
    "TEMPLATE_BORN_CLASSES",
]

REPO_CLASSES = (
    "core",
    "enforcement-suite",
    "impl-plugin",
    "driver-plugin",
    "library",
    "console",
    "control-plane-tool",
)

ALL_CLASSES: frozenset[str] = frozenset(REPO_CLASSES)
# The pin-and-bump web splits into two shim obligations, because the
# console (livespec-console-beads-fabro) is a pin CONSUMER, not a
# producer: its toolchain gates come from livespec-dev-tooling, so it
# carries the dev-tooling pin (see DEV_TOOLING_PIN_CLASSES) and ships the
# two RECEIVING shims (bump-pin-from-dispatch + pin-freshness) that keep
# that pin fresh — but it ships NO release-dispatch PRODUCER shim, because
# it produces no consumable release for a downstream repo to pin
# (livespec-dev-tooling contracts.md §"Bump-pin policy"; livespec-oq9w
# Option B).
#
# `PIN_WEB_CLASSES` is therefore specifically the set carrying the
# release-dispatch PRODUCER shim — every class EXCEPT the console. The
# exemption is the CONSOLE's specifically, NOT the Control Plane's: the
# sibling Control-Plane class `control-plane-tool` ships an operator tool
# whose gates come from this library and produces its own release, so it
# stays in the producer web. Read the subtraction literally — one class is
# named, not a plane.
PIN_WEB_CLASSES = ALL_CLASSES - {"console"}
# `RECEIVING_SHIM_CLASSES` carries the two RECEIVING shims
# (bump-pin-from-dispatch + pin-freshness): the pin-web classes PLUS the
# console, which consumes the dev-tooling pin and so must keep it fresh.
# This equals ALL_CLASSES, but is written as the union so the intent —
# add the console back onto the receiving obligations while leaving it off
# the release-dispatch producer row — stays legible.
RECEIVING_SHIM_CLASSES = PIN_WEB_CLASSES | {"console"}
TEMPLATE_BORN_CLASSES = frozenset({"impl-plugin"})
# The dev-tooling-pin row excludes only the enforcement-suite class —
# dev-tooling cannot pin itself; every other class, the console included,
# carries a [tool.uv.sources] livespec-dev-tooling tag pin.
DEV_TOOLING_PIN_CLASSES = ALL_CLASSES - {"enforcement-suite"}
