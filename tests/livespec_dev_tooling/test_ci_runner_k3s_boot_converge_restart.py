"""A failed boot converge is started again by systemd, with no operator action.

`converge-ci-stack.service` is the one thing standing between an unattended
reboot of `poweredge-xubuntu` — the fleet's single k3s server, whose datastore is
tmpfs — and a cluster with no Kueue, no ARC and no runner scale sets. It was
`Type=oneshot` with systemd's default `Restart=no`, so ONE failed run was final:
the unit went inactive-dead, nothing retried, and every repository in the fleet
had no CI until a human noticed and ran `systemctl start` by hand.

That is not hypothetical. Measured 2026-10-12: the 11:58Z unattended reboot's
converge failed at step 4 in 35 s on a transient HTTP 504 from GitHub's edge. A
hand-started run at 12:01Z failed the same way; one at 12:02Z got through. A
single retry a minute later would have recovered the cluster unattended, and
nothing was there to perform it.

The sibling slices removed the two internet fetches that caused THAT failure
(see `test_ci_runner_k3s_boot_converge_offline_kueue.py` and
`test_ci_runner_k3s_boot_converge_offline_arc_charts.py`). This slice is the
general case: whatever the next transient turns out to be — a cluster object not
yet admitting, a webhook endpoint a second late, an API server still settling —
the unit heals itself instead of waiting for a person.

`Restart=on-failure` is the one restart mode a `Type=oneshot` unit may carry
(`always` and `on-success` are rejected for oneshot by systemd, and rightly: a
converge that SUCCEEDED and exited must stay exited). The burst window is
generous on purpose — the converge legitimately runs for minutes, so a tight
default `StartLimitBurst` would spend its attempts inside one slow boot and
land back in the state this slice exists to end — but it is still BOUNDED, so a
PERMANENT defect surfaces as a failed unit an operator can read rather than an
invisible restart loop.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UNIT = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "reconstruct" / "converge-ci-stack.service"

# A restart burst below this would be spent inside a single slow converge.
_MIN_BURST = 5
# And above this it stops being a rate limit; `0` means no limit at all.
_MAX_BURST = 50
# Seconds. Below this a retry re-enters whatever is still settling.
_MIN_BACKOFF = 5


def _unit_sections() -> dict[str, dict[str, str]]:
    """The unit file as `{section: {directive: value}}`, last value winning.

    Hand-parsed: systemd unit files are INI-shaped but `configparser` rejects
    the duplicate keys a unit may legitimately carry, and the shape in question
    is one `Key=value` per line under a `[Section]` header.
    """
    sections: dict[str, dict[str, str]] = {}
    current = ""
    for raw in _UNIT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        if not line or line.startswith("#") or "=" not in line or not current:
            continue
        key, _, value = line.partition("=")
        sections[current][key.strip()] = value.strip()
    assert sections, f"{_UNIT} parsed to no sections"
    return sections


def _seconds(*, value: str) -> int | None:
    """`value` as whole seconds, or None if it is not a bare-seconds interval."""
    match = re.fullmatch(r"(\d+)(s|sec|seconds?)?", value)
    return None if match is None else int(match.group(1))


def test_boot_converge_unit_restarts_itself_on_failure() -> None:
    restart = _unit_sections().get("Service", {}).get("Restart")
    assert restart == "on-failure", (
        "converge-ci-stack.service does not restart itself on failure "
        f"(Restart={restart!r}), so ONE transient failure at an unattended boot "
        "leaves the fleet's only k3s server with no Kueue, no ARC and no CI "
        "until an operator runs `systemctl start` by hand — what happened on "
        "2026-10-12, when the very next attempt would have succeeded"
    )


def test_boot_converge_unit_backs_off_between_restarts() -> None:
    raw = _unit_sections().get("Service", {}).get("RestartSec")
    assert raw is not None, (
        "converge-ci-stack.service declares no RestartSec, so it retries on "
        "systemd's 100ms default — fast enough to burn the whole start limit "
        "before anything it is waiting on has had time to settle"
    )
    backoff = _seconds(value=raw)
    assert backoff is not None and backoff >= _MIN_BACKOFF, (
        f"converge-ci-stack.service retries after {raw!r}, under the "
        f"{_MIN_BACKOFF}s floor a transient needs to clear"
    )


def test_boot_converge_unit_allows_a_generous_but_bounded_restart_burst() -> None:
    unit = _unit_sections().get("Unit", {})
    interval = unit.get("StartLimitIntervalSec")
    assert interval is not None and _seconds(value=interval) is not None, (
        "converge-ci-stack.service declares no StartLimitIntervalSec, so the "
        "burst below is counted against systemd's 10s default window — in "
        "which a converge that runs for minutes can never spend a second attempt"
    )
    raw_burst = unit.get("StartLimitBurst")
    assert raw_burst is not None, (
        "converge-ci-stack.service declares no StartLimitBurst, so it inherits "
        "a default tight enough to give up inside one slow boot"
    )
    assert raw_burst.isdigit(), f"StartLimitBurst={raw_burst!r} is not a count"
    burst = int(raw_burst)
    assert burst >= _MIN_BURST, (
        f"converge-ci-stack.service allows only {burst} start attempt(s) per "
        f"window, under the {_MIN_BURST} a converge that legitimately runs for "
        "minutes needs to retry a transient"
    )
    assert 0 < burst <= _MAX_BURST, (
        f"converge-ci-stack.service allows {burst or 'unlimited'} start "
        "attempt(s) per window. The limit must stay BOUNDED (0 disables it "
        "entirely), so a PERMANENT defect surfaces as a failed unit an operator "
        "can read rather than an invisible restart loop"
    )


def test_boot_converge_unit_is_still_a_oneshot() -> None:
    service = _unit_sections().get("Service", {})
    assert service.get("Type") == "oneshot", (
        "converge-ci-stack.service is no longer Type=oneshot. The self-restart "
        "must not be bought by turning the converge into a long-running "
        "service: it converges and exits, and `Restart=on-failure` is the one "
        "restart mode systemd accepts for a oneshot precisely because a "
        "SUCCESSFUL converge must stay exited"
    )
    assert service.get("Restart") not in {"always", "on-success"}, (
        "systemd rejects Restart=always and Restart=on-success for "
        "Type=oneshot, so this unit would fail to load at the next boot — the "
        "most expensive possible way to learn it"
    )
