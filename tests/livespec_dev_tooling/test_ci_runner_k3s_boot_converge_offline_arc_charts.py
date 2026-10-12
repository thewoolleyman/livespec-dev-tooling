"""The ARC charts the boot converge installs come from the host, not from ghcr.io.

Same shape as the Kueue half (see
`test_ci_runner_k3s_boot_converge_offline_kueue.py`) and the same 2026-10-12
incident: the k3s datastore is tmpfs, so `reconstruct/converge-ci-stack.sh`
re-installs the ARC controller and all eleven runner scale sets from scratch on
every boot — and it did that with `helm upgrade --install` against a remote OCI
registry. Two chart pulls from someone else's registry therefore sat on the path
of an unattended reboot, and a transient failure of either left the fleet with no
runners and no CI until an operator re-ran the converge by hand.

The fix moves the fetch to APPLY time, where an operator is present and a
failure is loud: the `ci_converge_unit` Ansible role `helm pull`s both
version-pinned charts into the installed artifact tree beside the values files,
and the converge installs them from those local tarballs. Unlike the Kueue
manifest the charts are not vendored into git — they are upstream binaries, and
the artifact tree on the host (`/usr/local/lib/ci-runner-k3s/`) is ordinary disk
that survives the reboot the tmpfs datastore does not.

That split is why these tests check the ROLE as well as the converge: with the
bytes living only on the host, the role is the only thing that puts them there,
and the pinned version has to agree across the two or the converge fail-closes
on a tarball nobody pulled. The chart tarball names the converge installs are
DERIVED here from the role's chart list and pinned version, so a bump to one
surface that misses the other fails this test rather than the next reboot.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_BOOT_CONVERGE = _PHASE2 / "reconstruct" / "converge-ci-stack.sh"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "ci_converge_unit"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"

# Where the pulled charts live inside the artifact tree, relative to it. Also
# the directory the role must CREATE: the copy tasks cannot see past a missing
# parent under `--check`, which is why the role lists its directories at all.
_CHARTS_SUBDIR = "arc/charts"


def _logical_lines(*, text: str) -> tuple[str, ...]:
    """`text`'s lines with backslash continuations joined into one line each.

    Every `helm upgrade --install` in the converge is written across four or
    five continued lines, so a per-physical-line scan would see the subcommand
    and the chart reference as unrelated.

    Done as ONE substitution over the whole text rather than by accumulating
    line by line, which leaves no end-of-text arm for a continuation no shell
    script ever ends on — the per-file coverage gate reads test modules too,
    and an arm this converge cannot reach is an arm nothing verifies.
    """
    return tuple(line.strip() for line in re.sub(r"\\\n[ \t]*", " ", text).splitlines())


def _helm_install_invocations() -> tuple[str, ...]:
    found = tuple(
        line
        for line in _logical_lines(text=_BOOT_CONVERGE.read_text(encoding="utf-8"))
        if line.startswith("helm upgrade --install")
    )
    assert found, f"{_BOOT_CONVERGE} runs no `helm upgrade --install`"
    return found


def _chart_reference(*, line: str, text: str) -> str:
    """The chart a `helm upgrade --install` logical line installs.

    helm takes the chart as its LAST positional argument. Resolved through one
    level of shell-variable indirection, because the converge names the chart
    through a variable at both the install site and the fail-closed guard beside
    it rather than repeating the path — the shape every other artifact in this
    script already uses.

    Both unresolvable shapes are ASSERTED rather than returned as a fallback
    value: each is a defect in the converge this module reads, not an input it
    should carry into a caller's comparison, and an assertion says which.
    """
    last = line.split()[-1]
    named = re.fullmatch(r'"\$\{?(\w+)\}?"', last)
    assert named is not None, (
        f"the chart argument {last!r} is not a shell-variable reference. The "
        "converge names each chart through a variable so the install site and "
        "the fail-closed guard beside it cannot disagree about the path"
    )
    assignment = re.search(rf'^{re.escape(named.group(1))}="([^"]*)"', text, re.MULTILINE)
    assert assignment is not None, (
        f"{last} is installed but assigned nowhere in {_BOOT_CONVERGE.name}, so "
        "the chart it names cannot be checked — or resolved at boot"
    )
    return assignment.group(1)


def _yaml_scalar(*, text: str, key: str) -> str | None:
    """The scalar value of a top-level `key:` in a flat defaults file."""
    match = re.search(rf'^{re.escape(key)}:\s*"?([^"\n]+?)"?\s*$', text, re.MULTILINE)
    return None if match is None else match.group(1)


def _yaml_string_list(*, text: str, key: str) -> tuple[str, ...]:
    """The entries of a top-level `key:` block sequence of plain scalars.

    Walks the whole file and leaves the sequence by clearing its flag rather
    than `break`ing, for the coverage reason `_logical_lines` records.
    """
    entries: list[str] = []
    in_block = False
    for line in text.splitlines():
        if line.startswith(f"{key}:"):
            in_block = True
            continue
        if not in_block:
            continue
        match = re.match(r"^\s+-\s+(\S+)\s*$", line)
        if match is None:
            in_block = False
            continue
        entries.append(match.group(1).strip('"'))
    return tuple(entries)


def _converge_chart_version() -> str:
    text = _BOOT_CONVERGE.read_text(encoding="utf-8")
    match = re.search(r'^ARC_CHART_VERSION="([^"]+)"', text, re.MULTILINE)
    assert match is not None, f"{_BOOT_CONVERGE} declares no ARC_CHART_VERSION"
    return match.group(1)


def test_boot_converge_installs_no_chart_from_a_remote_registry() -> None:
    converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    assert "oci://" not in converge, (
        "the boot converge still names a remote OCI chart registry, so an "
        "unattended reboot's ARC install depends on that registry answering — "
        "the failure mode that left the fleet with no runners and no CI on "
        "2026-10-12. Pull the pinned charts at apply time instead and install "
        "them from the artifact tree"
    )


def test_every_boot_converge_helm_install_names_a_local_pinned_chart() -> None:
    converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    charts = {
        line: _chart_reference(line=line, text=converge) for line in _helm_install_invocations()
    }
    offenders = [
        f"{line} -> {chart}"
        for line, chart in charts.items()
        if "://" in chart or ".tgz" not in chart or "${ARC_CHART_VERSION}" not in chart
    ]
    assert not offenders, (
        "boot-converge `helm upgrade --install` invocation(s) that do not "
        "install a version-pinned chart tarball from the artifact tree, so they "
        f"reach the network at boot: {offenders}"
    )


def test_boot_converge_fails_closed_on_a_chart_the_role_never_pulled() -> None:
    converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    chart_vars = sorted(set(re.findall(r"^(ARC_\w*CHART)=", converge, re.MULTILINE)))
    assert chart_vars, (
        f"{_BOOT_CONVERGE} resolves no ARC chart tarball path, so there is "
        "nothing for it to install locally"
    )
    unguarded = [name for name in chart_vars if f'[ -f "${{{name}}}" ]' not in converge]
    assert not unguarded, (
        "ARC chart path(s) the boot converge installs without first asserting "
        "the file is there, so an artifact tree that predates the apply-time "
        "pull fails inside helm with wording that names neither the missing "
        f"file nor the role that supplies it: {unguarded}"
    )


def test_ci_converge_unit_role_creates_the_chart_directory() -> None:
    directories = _yaml_string_list(
        text=_ROLE_DEFAULTS.read_text(encoding="utf-8"), key="ci_converge_unit_directories"
    )
    assert _CHARTS_SUBDIR in directories, (
        f"the ci_converge_unit role does not create {_CHARTS_SUBDIR!r} in the "
        "installed artifact tree, so the chart pull has nowhere to land and "
        "`--check` cannot see past the missing parent"
    )


def test_ci_converge_unit_role_pulls_the_charts_the_boot_converge_installs() -> None:
    defaults = _ROLE_DEFAULTS.read_text(encoding="utf-8")
    role_version = _yaml_scalar(text=defaults, key="ci_converge_unit_arc_chart_version")
    assert role_version is not None, (
        "the ci_converge_unit role pins no ARC chart version, so nothing says "
        "WHICH chart it should pull onto the host"
    )
    assert role_version == _converge_chart_version(), (
        f"the ci_converge_unit role pins ARC chart {role_version} while the boot "
        f"converge installs {_converge_chart_version()}; the converge would "
        "fail closed on a tarball the role never pulled — bump them together"
    )
    charts = _yaml_string_list(text=defaults, key="ci_converge_unit_arc_charts")
    assert charts, "the ci_converge_unit role names no ARC charts to pull"
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")
    assert "pull" in tasks and _CHARTS_SUBDIR in tasks, (
        "the ci_converge_unit role declares the charts to pull but no task "
        f"pulls them into {_CHARTS_SUBDIR}, so the boot converge installs from "
        "an empty directory"
    )
    converge = _BOOT_CONVERGE.read_text(encoding="utf-8")
    uninstalled = [
        chart for chart in charts if f"{chart}-${{ARC_CHART_VERSION}}.tgz" not in converge
    ]
    assert not uninstalled, (
        "chart(s) the ci_converge_unit role pulls onto the host that the boot "
        f"converge never installs from the artifact tree: {uninstalled}"
    )
