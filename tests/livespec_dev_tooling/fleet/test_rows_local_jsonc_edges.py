"""Green-leg edges for `_rows_local_jsonc.py`'s railway conversion.

A `*_edges.py` sibling rather than additions to `test_rows_local_jsonc.py`,
because that file is byte-identity-bound to its own Red commit.

Both branches here are ones the conversion CREATED or FREED, and neither is
reachable through the fixtures the mirror-paired file already carries:

- The raw-text anchor miss. `_fill_connection`'s `None` used to cover two
  conditions — an unresolvable `implementation.plugin` and a block key the
  line-anchored regex could not find — and the ghost-plugin fixture covered
  it through the FIRST. The caller now resolves the plugin on the railway,
  so only the second reaches `_fill_connection`, and reaching it needs a
  config whose block key is not at the start of its own line.
- The duplicate-key regression. A `connection` key present but not an object
  read as "no connection block", so the row machine-filled a SECOND
  `connection` into a block that already had one. The row is supposed never
  to auto-edit a config it does not understand.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._context import RowFinding
from livespec_dev_tooling.fleet._local_context import LocalContext, default_command_runner
from livespec_dev_tooling.fleet._rows_local_jsonc import reconcile_livespec_jsonc_complete

if TYPE_CHECKING:
    from pathlib import Path

_BEADS_FULL = textwrap.dedent(
    """\
    # Beads Configuration File
    dolt.server-host: 127.0.0.1
    dolt.server-port: 3307
    dolt.server-user: widget
    dolt.database: widget
    dolt.prefix: widget
    """
)

# `implementation.plugin` RESOLVES and its block IS an object, so the lookup
# reaches `_fill_connection` — but the whole config is ONE line, so the block
# key has other content before it and the LINE-ANCHORED insertion regex finds
# no anchor. A key/brace split across lines does NOT miss: the pattern's `\s*`
# spans newlines, which the first draft of this fixture got wrong and this
# test caught.
_CONFIG_UNANCHORED_BLOCK = (
    '{ "harnesses": { "claude": { "status": "supported" } }, '
    '"implementation": { "plugin": "widget-impl" }, '
    '"widget-impl": { "format": "beads" } }\n'
)

# The impl-plugin block DECLARES a `connection`, and it is a string.
_CONFIG_MALFORMED_CONNECTION = textwrap.dedent(
    """\
    {
      "harnesses": {
        "claude": { "status": "supported", "canonical_command": "/livespec:doctor" }
      },
      "implementation": { "plugin": "widget-impl" },
      "widget-impl": {
        "connection": "127.0.0.1:3307"
      }
    }
    """
)


def _checkout(*, tmp_path: Path, jsonc: str) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(jsonc, encoding="utf-8")
    (tmp_path / ".beads").mkdir(exist_ok=True)
    (tmp_path / ".beads" / "config.yaml").write_text(_BEADS_FULL, encoding="utf-8")
    return tmp_path


def _ctx(*, checkout: Path) -> LocalContext:
    return LocalContext(checkout=checkout, home=checkout / "home", run=default_command_runner)


def test_unanchored_block_key_warns_and_does_not_rewrite(*, tmp_path: Path) -> None:
    """A resolvable plugin whose block key the regex cannot anchor on warns.

    This is the branch the conversion FREED: it was reachable before only
    through the same `None` an unresolvable `implementation.plugin`
    produced, so no test ever proved the raw-text miss specifically.
    """
    checkout = _checkout(tmp_path=tmp_path, jsonc=_CONFIG_UNANCHORED_BLOCK)

    outcome = reconcile_livespec_jsonc_complete(ctx=_ctx(checkout=checkout))

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "was not found in the raw text" in outcome.message
    assert "author the connection block by hand" in outcome.message
    # Nothing was written: the verb never auto-edits a config it cannot anchor.
    assert (checkout / ".livespec.jsonc").read_text(encoding="utf-8") == _CONFIG_UNANCHORED_BLOCK


def test_malformed_connection_warns_instead_of_writing_a_second_key(*, tmp_path: Path) -> None:
    """A present-but-not-an-object `connection` is a defect, not an absence.

    Before the conversion this reached `_fill_connection` and succeeded —
    the regex anchors on the block key, which is perfectly findable here —
    so the row wrote a second `connection` key into the block. The file
    below is the positive control for that: if the row regressed to
    treating a malformed `connection` as absent, the written text would
    carry TWO `connection` keys and this assertion fires.
    """
    checkout = _checkout(tmp_path=tmp_path, jsonc=_CONFIG_MALFORMED_CONNECTION)

    outcome = reconcile_livespec_jsonc_complete(ctx=_ctx(checkout=checkout))

    assert isinstance(outcome, RowFinding)
    assert outcome.severity == "warning"
    assert "not an object" in outcome.message
    written = (checkout / ".livespec.jsonc").read_text(encoding="utf-8")
    assert written == _CONFIG_MALFORMED_CONNECTION
    assert written.count('"connection"') == 1
