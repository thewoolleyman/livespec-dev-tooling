"""No `ansible.builtin.copy` task passes a sha256 pin to its `checksum:`.

`copy` verifies a SHA-1 checksum only. A sha256 pin passed to it fails the real apply with
"Copied file does not match the expected checksum" while check mode, which skips the
comparison, reports clean (livespec-dev-tooling-fwtuxo, the vps apply of 2026-11-21).
A sha256 pin belongs on `get_url` as `sha256:<hex>`, or in a `stat` plus `assert` as in
`ansible/roles/btop_loop`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_ROLES = Path(__file__).resolve().parents[2] / "ansible" / "roles"
_COPY_TASK = re.compile(r"^(?P<indent> *)ansible\.builtin\.copy:\s*$")
_CHECKSUM = re.compile(r"^\s+checksum:\s*(?P<value>.+)$")


def _copy_checksums(*, text: str) -> list[str]:
    """The `checksum:` values set directly under each `ansible.builtin.copy:` in `text`."""
    lines = text.splitlines()
    found: list[str] = []
    for index, line in enumerate(lines):
        match = _COPY_TASK.match(line)
        if match is None:
            continue
        depth = len(match["indent"])
        for body in lines[index + 1 :]:
            if body.strip() and len(body) - len(body.lstrip()) <= depth:
                break
            hit = _CHECKSUM.match(body)
            if hit is not None:
                found.append(hit["value"].strip())
    return found


def test_the_checker_finds_a_sha256_pin_passed_to_copy() -> None:
    sample = (
        "- name: x\n"
        "  ansible.builtin.copy:\n"
        "    src: a\n"
        '    checksum: "{{ role_pinned_sha256 }}"\n'
    )
    assert _copy_checksums(text=sample) == ['"{{ role_pinned_sha256 }}"']


def test_no_committed_role_passes_a_sha256_pin_to_copy() -> None:
    offenders = [
        f"{path.relative_to(_ROLES)}: {value}"
        for path in sorted(_ROLES.glob("*/tasks/*.yml"))
        for value in _copy_checksums(text=path.read_text(encoding="utf-8"))
        if "sha256" in value.lower()
    ]
    assert offenders == [], offenders
