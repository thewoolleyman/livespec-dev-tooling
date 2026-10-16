"""k3s's EFFECTIVE resync intervals, and the observation window they set.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Preflight" (this repository).
Governing design: `docs/docker-engine-guard-design.md` R8 ("the resync
window is derived from the effective intervals recorded with their
source … never from defaults alone, plus two minutes") and F7 ("k3s's
resync settings are read from `/etc/rancher/k3s/config.yaml` and its
drop-ins, not from the unit's `ExecStart`").

WHY THE WINDOW IS DERIVED AT ALL. k3s's reconcilers rewrite this host's
firewall on a period of their own. A Docker install that broke the pod
network would be repaired, or re-broken, by the next sweep — so a window
shorter than one full period of the SLOWEST reconciler can report a host
as healthy that the next sweep takes down, on a machine reachable only
over Tailscale. Two minutes beyond that period is the room to see the
sweep's result rather than merely to outlive it.

WHY THE DEFAULTS ARE INTERVALS AND NOT A FALLBACK. A setting no file
mentions is still IN FORCE at its component's default, so it is part of
the effective set and is recorded with a source saying so. R8's "never
from defaults alone" is satisfied by READING the files, not by refusing
to know what a file left unsaid: a host with an empty configuration has
effective intervals, and they are the defaults.

WHY A SMALL YAML SUBSET AND NOT A PARSER. Nothing beyond the standard
library is importable where this code runs (the model module records
why), and k3s's own configuration uses exactly two shapes for these
settings: a top-level scalar, and a top-level argument LIST. Both are
read; a nested mapping is not, because none of these settings lives in
one.

Stdlib only, Python 3.10 syntax.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__: list[str] = [
    "ARG_LIST_KEYS",
    "DEFAULT_INTERVALS",
    "DEFAULT_SOURCE",
    "K3S_CONFIG",
    "K3S_CONFIG_DROPINS",
    "MAX_RESYNC_SECONDS",
    "SCALAR_KEYS",
    "SYNC_PERIOD_ARGUMENT",
    "WINDOW_MARGIN_SECONDS",
    "ResyncInterval",
    "configuration_files",
    "declared_intervals",
    "duration_seconds",
    "excessive_resync_intervals",
    "read_resync_intervals",
    "resync_window_seconds",
]

# Root-only, and the authoritative place: the unit's `ExecStart` carries
# what the installer put there, which is not what k3s is running with
# once a drop-in has been added (design F7).
K3S_CONFIG: Final[Path] = Path("/etc/rancher/k3s/config.yaml")
K3S_CONFIG_DROPINS: Final[Path] = Path("/etc/rancher/k3s/config.yaml.d")

# The argument both firewall reconcilers take their period from, as k3s
# passes it through to them.
SYNC_PERIOD_ARGUMENT: Final[str] = "iptables-sync-period"

# The two argument lists that period can arrive in, and the one scalar
# setting flannel's own reconcile period arrives as.
ARG_LIST_KEYS: Final[tuple[str, ...]] = (
    "kube-proxy-arg",
    "kube-router-arg",
)
SCALAR_KEYS: Final[tuple[str, ...]] = ("flannel-iptables-resync",)

# What each setting is when no file mentions it, measured on this fleet's
# k3s (design, "Window W"): the network-policy controller resyncs every
# five minutes, kube-proxy every thirty seconds, flannel every five.
DEFAULT_INTERVALS: Final[Mapping[str, float]] = {
    "flannel-iptables-resync": 5.0,
    "kube-proxy-arg iptables-sync-period": 30.0,
    "kube-router-arg iptables-sync-period": 300.0,
}

# The source recorded for an interval no file declared. It is a source
# like any other rather than an absence, because the interval is in
# force either way and an operator reading the record has to be able to
# tell "nobody set this" from "a drop-in set this".
DEFAULT_SOURCE: Final[str] = "<component default>"

# The ceiling the preflight refuses above, and the room added past the
# slowest period to make the window.
MAX_RESYNC_SECONDS: Final[int] = 300
WINDOW_MARGIN_SECONDS: Final[int] = 120

# A Go duration: one or more unsigned counts each with an optional unit,
# as `30s`, `5m`, `1m30s` and a bare second count are all written. The
# whole value must match, so a typo (`everyfiveminutes`) is not a
# duration at all rather than a duration of zero.
_UNIT_SECONDS: Final[Mapping[str, float]] = {
    "": 1.0,
    "h": 3600.0,
    "m": 60.0,
    "ms": 1e-3,
    "ns": 1e-9,
    "s": 1.0,
    "us": 1e-6,
    "µs": 1e-6,
}
_COUNT: Final[str] = r"\d+(?:\.\d+)?(?:ns|us|µs|ms|s|m|h)?"
_DURATION: Final[re.Pattern[str]] = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)?")
_WHOLE_DURATION: Final[re.Pattern[str]] = re.compile(f"(?:{_COUNT})+")

_LIST_ITEM: Final[str] = "- "
_ASSIGNMENT: Final[str] = "="


@dataclass(frozen=True, kw_only=True)
class ResyncInterval:
    """One effective resync interval: which setting, how long, read from where.

    The SOURCE is carried because a refusal has to be actionable: "a
    resync interval is above five minutes" leaves an operator with
    nothing to edit, while a drop-in's path names the file to change.
    """

    setting: str
    seconds: float
    source: str


def duration_seconds(*, text: str) -> tuple[float, ...]:
    """`text` as a count of seconds, or NOTHING when it is not a duration.

    A tuple rather than an optional float so a caller can use it inside
    a comprehension without a branch of its own: a value that is not a
    duration simply contributes no interval, which is right — the
    component's default is still in force and is already recorded.
    """
    body = text.strip()
    if not _WHOLE_DURATION.fullmatch(body):
        return ()
    return (sum(float(count) * _UNIT_SECONDS[unit] for count, unit in _DURATION.findall(body)),)


def _declarations(*, text: str) -> Mapping[str, tuple[str, ...]]:
    """One k3s configuration file's top-level keys, each with its values.

    Comments and blank rows contribute nothing, a `key: value` row
    contributes one value, and a `- item` row contributes one value to
    the key above it. That is the whole subset these settings need.
    """
    found: dict[str, list[str]] = {}
    key = ""
    for raw in text.splitlines():
        row = raw.split("#", 1)[0].strip()
        if row.startswith(_LIST_ITEM):
            found.setdefault(key, []).append(row[len(_LIST_ITEM) :].strip().strip("\"'"))
        elif ":" in row:
            name, _, value = row.partition(":")
            key = name.strip()
            values = found.setdefault(key, [])
            if value.strip():
                values.append(value.strip().strip("\"'"))
    return {name: tuple(values) for name, values in found.items()}


def declared_intervals(*, path: Path) -> tuple[ResyncInterval, ...]:
    """Every resync interval one configuration file declares, with that file as source.

    An argument-list entry counts only when its NAME is the sync-period
    argument, read before the first `=` and with any leading dashes
    stripped: `proxy-mode=iptables` sits in the same list and must not
    be read as a period.
    """
    declarations = _declarations(text=path.read_text(encoding="utf-8"))
    found: list[ResyncInterval] = []
    for key in SCALAR_KEYS:
        found.extend(
            ResyncInterval(setting=key, seconds=seconds, source=str(path))
            for value in declarations.get(key, ())
            for seconds in duration_seconds(text=value)
        )
    for key in ARG_LIST_KEYS:
        found.extend(
            ResyncInterval(
                setting=f"{key} {SYNC_PERIOD_ARGUMENT}", seconds=seconds, source=str(path)
            )
            for value in declarations.get(key, ())
            if value.partition(_ASSIGNMENT)[0].lstrip("-") == SYNC_PERIOD_ARGUMENT
            for seconds in duration_seconds(text=value.partition(_ASSIGNMENT)[2])
        )
    return tuple(found)


def configuration_files(*, config: Path, dropins: Path) -> tuple[Path, ...]:
    """The base configuration and every drop-in, in the order k3s reads them.

    A missing base file and a missing drop-in directory both contribute
    nothing: a host whose k3s was installed with flags alone has no
    configuration file, and its effective intervals are the defaults.
    """
    base = (config,) if config.is_file() else ()
    return (*base, *sorted(dropins.glob("*.yaml")))


def read_resync_intervals(
    *, config: Path = K3S_CONFIG, dropins: Path = K3S_CONFIG_DROPINS
) -> tuple[ResyncInterval, ...]:
    """Every effective resync interval on this host, each with its source.

    Nothing is merged away. A setting declared in both the base file and
    a drop-in is recorded twice, and that is safe in exactly one
    direction: the window is the LARGEST of the recorded intervals, so
    an extra declaration can only lengthen the window, never shorten it
    — and a window that is too long costs time while a window that is
    too short reports a host as healthy that the next sweep takes down.
    """
    found = [
        ResyncInterval(setting=setting, seconds=DEFAULT_INTERVALS[setting], source=DEFAULT_SOURCE)
        for setting in sorted(DEFAULT_INTERVALS)
    ]
    for path in configuration_files(config=config, dropins=dropins):
        found.extend(declared_intervals(path=path))
    return tuple(found)


def resync_window_seconds(*, intervals: Sequence[ResyncInterval]) -> int:
    """The observation window: the largest effective interval plus two minutes."""
    longest = max((interval.seconds for interval in intervals), default=0.0)
    return round(longest) + WINDOW_MARGIN_SECONDS


def excessive_resync_intervals(*, intervals: Sequence[ResyncInterval]) -> tuple[str, ...]:
    """Every effective interval above five minutes, named with its source.

    Above that ceiling the window the guard would have to hold open --
    and with it the time Docker runs unconfirmed on a host nobody can
    reach physically -- grows past what the dead-man's budgets cover, so
    the install is refused rather than stretched to fit.
    """
    return tuple(
        f"{interval.setting} is {interval.seconds:g}s in {interval.source}, "
        f"above the {MAX_RESYNC_SECONDS}s maximum"
        for interval in intervals
        if interval.seconds > MAX_RESYNC_SECONDS
    )
