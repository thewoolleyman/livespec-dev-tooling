"""Python marker carriers must be comments for the exact incident identity."""

from __future__ import annotations

import pytest

from livespec_dev_tooling.incident_markers import validate_python_repair_marker

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw

_ITEM = "livespec-dev-tooling-gvylzw"
_MARKER = "# EXPEDITED_INCIDENT_RESPONSE flag: " + _ITEM


@pytest.mark.parametrize(
    ("source", "locations"),
    [
        (_MARKER + "\nvalue = 1\n", (1,)),
        ("value = 1  " + _MARKER + "\n", (1,)),
        ("def repair():\n    " + _MARKER + "\n    return 1\n", (2,)),
        (_MARKER + "\n" + _MARKER + "  \n", (1, 2)),
        (_MARKER, (1,)),
    ],
)
def test_exact_comment_carriers(source: str, locations: tuple[int, ...]) -> None:
    result = validate_python_repair_marker(source=source, incident_item_id=_ITEM)
    assert result.value_or(()) == locations


@pytest.mark.parametrize(
    "source",
    [
        "",
        "value = 1\n",
        "message = " + repr(_MARKER) + "\n",
        '"""' + _MARKER + '\n"""\n',
        "# explanation " + _MARKER + "\n",
        "# EXPEDITED_INCIDENT_RESPONSE flag: another-incident\n",
        _MARKER + "-other\n",
        _MARKER + " extra\n",
        "# EXPEDITED_INCIDENT_RESPONSE flag:" + _ITEM + "\n",
        "# EXPEDITED_INCIDENT_RESPONSE flag:  " + _ITEM + "\n",
    ],
)
def test_text_and_foreign_markers_do_not_supply_provenance(source: str) -> None:
    result = validate_python_repair_marker(source=source, incident_item_id=_ITEM)
    assert result.failure().code == "missing-incident-marker"


@pytest.mark.parametrize("item", ["", " item", "item ", "item\n", "item\x00", "item\x7f"])
def test_invalid_identity_never_builds_a_marker(item: str) -> None:
    result = validate_python_repair_marker(source=_MARKER, incident_item_id=item)
    assert result.failure().code == "invalid-incident-marker-identity"


@pytest.mark.parametrize("source", [_MARKER + '\n"""unterminated', _MARKER + "\nvalue = (\n"])
def test_a_marker_before_unreadable_source_does_not_pass(source: str) -> None:
    result = validate_python_repair_marker(source=source, incident_item_id=_ITEM)
    assert result.failure().code == "unreadable-incident-marker-source"
