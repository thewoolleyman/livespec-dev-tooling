"""Narration for authority members a delegated pre-push runs on the host."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from typing import cast

import pytest
import structlog

from livespec_dev_tooling._gate_host_authority import HostAuthorityRun

__all__: list[str] = []

_MODULE_NAME = "livespec_dev_tooling._gate_host_authority"
_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_MEMBER = "check-widget-approval"


def test_a_passing_host_authority_member_is_narrated_on_its_own_line(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """A delegated pre-push makes a host-side pass visible to its operator."""
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(),
    )
    module = importlib.import_module(_MODULE_NAME)

    assert hasattr(module, "narrate_host_authority_passes")
    narrate = cast(Callable[..., None], module.narrate_host_authority_passes)
    narrate(
        ran=(
            HostAuthorityRun(
                member=_MEMBER,
                tree_hash=_TREE,
                returncode=0,
                detail="",
            ),
        )
    )

    captured = capsys.readouterr()
    lines = (captured.out + captured.err).splitlines()
    assert len(lines) == 1
    line = json.loads(lines[0])
    assert line["member"] == _MEMBER
    assert line["tree_hash"] == _TREE
    assert line["passed"] is True
    assert "ran on the pushing host" in line["event"]
