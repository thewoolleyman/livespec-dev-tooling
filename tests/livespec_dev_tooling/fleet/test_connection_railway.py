"""The four `_connection` lookups put every defect on the failure track.

Each of the four carried a `None` covering between two and six distinct
conditions (`plan/rop-railway-enforcement/qndn-75-triage.md` rows 28-29
and §4d-BIS). These assert the conversion at each function's OWN seam:
the composed caller short-circuits, so a test driving only
`connection_block` would leave most of the branches unreached.

The success/absence split is the load-bearing half. `named_plugin_connection`
and `connection_block` still answer `None`, but that `None` now carries
EXACTLY ONE condition — the resolved block declares no `connection` — which
is the ratified `tag_version_component` absence shape. Every other condition
left on the failure track.
"""

from __future__ import annotations

from returns.result import Failure, Success

from livespec_dev_tooling.fleet._connection import (
    connection_block,
    impl_plugin_name,
    named_plugin_connection,
    parse_document,
)

_CONNECTION = {
    "server_host": "127.0.0.1",
    "server_port": 3307,
    "server_user": "widget",
    "database": "widget",
    "prefix": "widget",
}


def _document(*, connection: bool = True) -> dict[str, object]:
    block: dict[str, object] = {"dispatcher": {"acceptance_mode": "ai-only"}}
    if connection:
        block["connection"] = dict(_CONNECTION)
    return {"implementation": {"plugin": "widget"}, "widget": block}


def test_parse_document_returns_the_object_map_on_the_success_track() -> None:
    assert parse_document(text='{"a": 1}\n') == Success({"a": 1})


def test_parse_document_fails_on_text_that_is_not_jsonc() -> None:
    result = parse_document(text="{ this is not valid json at all ::: ")
    assert isinstance(result, Failure)
    assert "not parseable as JSONC" in result.failure().detail


def test_parse_document_fails_on_a_root_that_is_not_an_object() -> None:
    """A parseable document whose root is a list is a DIFFERENT defect.

    Before the conversion both shapes shared one `None`, so the caller
    reported "unparseable as JSONC or its root is not a JSON object" —
    one message for two edits.
    """
    result = parse_document(text="[1, 2, 3]\n")
    assert isinstance(result, Failure)
    assert "not a JSON object" in result.failure().detail
    assert "list" in result.failure().detail


def test_impl_plugin_name_returns_the_declared_name() -> None:
    assert impl_plugin_name(document=_document()) == Success("widget")


def test_impl_plugin_name_fails_when_the_document_declares_no_implementation() -> None:
    result = impl_plugin_name(document={"harnesses": {}})
    assert isinstance(result, Failure)
    assert "no `implementation` block" in result.failure().detail


def test_impl_plugin_name_fails_when_implementation_is_not_an_object() -> None:
    result = impl_plugin_name(document={"implementation": "widget"})
    assert isinstance(result, Failure)
    assert "`implementation` is str, not an object" in result.failure().detail


def test_impl_plugin_name_fails_when_the_plugin_key_is_absent() -> None:
    result = impl_plugin_name(document={"implementation": {"harness": "claude"}})
    assert isinstance(result, Failure)
    assert "declares no `plugin` key" in result.failure().detail


def test_impl_plugin_name_fails_when_the_plugin_key_is_not_a_string() -> None:
    result = impl_plugin_name(document={"implementation": {"plugin": ["widget"]}})
    assert isinstance(result, Failure)
    assert "`implementation.plugin` is list, not a string" in result.failure().detail


def test_named_plugin_connection_returns_the_connection_dict() -> None:
    assert named_plugin_connection(document=_document()) == Success(_CONNECTION)


def test_named_plugin_connection_answers_none_when_the_block_declares_no_connection() -> None:
    """The ONE surviving `None`, and it is an ANSWER rather than a defect.

    This is the state the local reconcile row machine-fills from
    `.beads/config.yaml`, so putting it on the failure track would put the
    verb's normal case there.
    """
    assert named_plugin_connection(document=_document(connection=False)) == Success(None)


def test_named_plugin_connection_fails_when_the_named_block_does_not_exist() -> None:
    result = named_plugin_connection(document={"implementation": {"plugin": "ghost"}})
    assert isinstance(result, Failure)
    assert "not a top-level block" in result.failure().detail


def test_named_plugin_connection_fails_when_the_named_block_is_not_an_object() -> None:
    result = named_plugin_connection(document={"implementation": {"plugin": "w"}, "w": [1]})
    assert isinstance(result, Failure)
    assert "top-level `w` is list, not an object" in result.failure().detail


def test_named_plugin_connection_fails_when_connection_is_present_but_not_an_object() -> None:
    """A malformed `connection` is a DEFECT, and it used to read as an absence.

    That collapse was a fail-WRONG rather than a fail-open: the local
    reconcile row read the `None` as "no connection block", machine-filled
    one, and wrote a SECOND `connection` key into a block that already had
    one.
    """
    document: dict[str, object] = {"implementation": {"plugin": "w"}, "w": {"connection": "oops"}}
    result = named_plugin_connection(document=document)
    assert isinstance(result, Failure)
    assert "`w.connection` is str, not an object" in result.failure().detail


def test_named_plugin_connection_propagates_the_impl_plugin_failure_verbatim() -> None:
    result = named_plugin_connection(document={"harnesses": {}})
    assert isinstance(result, Failure)
    assert "no `implementation` block" in result.failure().detail


def test_connection_block_returns_the_named_plugin_connection() -> None:
    assert connection_block(
        text='{"implementation": {"plugin": "w"}, "w": {"connection": {}}}'
    ) == (Success({}))


def test_connection_block_fails_when_the_document_is_unusable() -> None:
    result = connection_block(text="{ this is not valid json at all ::: ")
    assert isinstance(result, Failure)
    assert "not parseable as JSONC" in result.failure().detail


def test_connection_block_answers_none_when_no_block_carries_a_connection() -> None:
    """Parsed, walked, and genuinely nothing found — the member is not beads-backed."""
    assert connection_block(text='{"harnesses": {"claude": {}}}') == Success(None)


def test_connection_block_falls_back_to_scanning_when_the_impl_plugin_link_is_broken() -> None:
    """A broken `implementation.plugin` link is NOT the fallback scan's failure.

    The scan exists precisely for documents with no well-formed impl-plugin
    declaration, so `named_plugin_connection`'s failure is answered by the
    scan rather than propagated — and the scan then answers definitively.
    """
    result = connection_block(text='{"other": {"connection": {"database": "widget"}}}')
    assert result == Success({"database": "widget"})
