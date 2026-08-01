"""Tests for `livespec_dev_tooling/fleet/_rows_beads.py`.

The tenant-connection-consistency row asserts that a beads-backed
member's `.beads/config.yaml` (read by `bd`) and its `.livespec.jsonc`
impl-plugin `connection` block (read by the plugin) agree on the five
load-bearing tenant-connection fields. Exercised across pass (both
files agree), finding (a field disagrees), and skip (either file or the
connection block absent — not every member is beads-backed) through a
canned-response `FleetContext` (no network, no real `gh`).
"""

from __future__ import annotations

import textwrap

from _gh_railway import lift_gh

from livespec_dev_tooling.fleet._context import (
    EXCLUDED_NOTE_PREFIX,
    FleetContext,
    FleetMember,
    GhResult,
    GhRunner,
    RowFinding,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_beads import (
    BEADS_CONFIG_PATH,
    LIVESPEC_JSONC_PATH,
    assert_tenant_connection_consistency,
)

__all__: list[str] = []


_MEMBER = FleetMember(repo="widget", repo_class="impl-plugin")
_BEADS_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.beads/config.yaml?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)
_JSONC_ARGS: tuple[str, ...] = (
    "api",
    "repos/acme/widget/contents/.livespec.jsonc?ref=master",
    "-H",
    "Accept: application/vnd.github.raw",
)


def make_context(*, table: dict[tuple[str, ...], GhResult]) -> FleetContext:
    """A `FleetContext` for owner `acme` over a canned-response runner."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        del stdin
        return table.get(tuple(args), GhResult(returncode=1, stdout="", stderr="no canned"))

    runner: GhRunner = run
    return FleetContext(owner="acme", run_gh=lift_gh(runner))


def _beads_config(
    *,
    server_host: str = "127.0.0.1",
    server_port: str = "3307",
    server_user: str = "widget",
    database: str = "widget",
    prefix: str = "widget",
) -> str:
    return textwrap.dedent(
        f"""\
        # Beads Configuration File
        dolt.mode: server
        dolt.server-host: {server_host}
        dolt.server-port: {server_port}
        dolt.server-user: {server_user}
        dolt.database: {database}
        dolt.prefix: {prefix}
        """
    )


def _livespec_jsonc(
    *,
    server_host: str = "127.0.0.1",
    server_port: int = 3307,
    server_user: str = "widget",
    database: str = "widget",
    prefix: str = "widget",
    with_connection: bool = True,
) -> str:
    connection = (
        textwrap.dedent(
            f"""\
            ,
                "connection": {{
                  "prefix": "{prefix}",
                  "database": "{database}",
                  "server_user": "{server_user}",
                  "server_host": "{server_host}",
                  "server_port": {server_port}
                }}"""
        )
        if with_connection
        else ""
    )
    return textwrap.dedent(
        f"""\
        // hermetic test config
        {{
          "implementation": {{ "plugin": "livespec-orchestrator-beads-fabro" }},
          "livespec-orchestrator-beads-fabro": {{
            "format": "beads"{connection}
          }}
        }}
        """
    )


def _ok(*, text: str) -> GhResult:
    return GhResult(returncode=0, stdout=text, stderr="")


def test_path_constants_point_at_the_two_connection_sources() -> None:
    assert BEADS_CONFIG_PATH == ".beads/config.yaml"
    assert LIVESPEC_JSONC_PATH == ".livespec.jsonc"


def test_consistent_connection_passes() -> None:
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text=_beads_config()),
            _JSONC_ARGS: _ok(text=_livespec_jsonc()),
        }
    )
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_mismatched_field_is_finding_naming_the_key() -> None:
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text=_beads_config(server_port="3307")),
            _JSONC_ARGS: _ok(text=_livespec_jsonc(server_port=9999)),
        }
    )
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "server_port" in outcome.message
    assert "widget" in outcome.message


def test_multiple_mismatched_fields_named_in_finding() -> None:
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text=_beads_config(database="alpha", prefix="alpha")),
            _JSONC_ARGS: _ok(text=_livespec_jsonc(database="beta", prefix="gamma")),
        }
    )
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowFinding)
    assert "database" in outcome.message
    assert "prefix" in outcome.message


def test_missing_beads_config_skips() -> None:
    ctx = make_context(table={_JSONC_ARGS: _ok(text=_livespec_jsonc())})
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)
    assert "widget" in outcome.reason


def test_missing_livespec_jsonc_skips() -> None:
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config())})
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)


def test_missing_connection_block_is_excluded() -> None:
    """Read, and definitively carries no connection block: INAPPLICABLE."""
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text=_beads_config()),
            _JSONC_ARGS: _ok(text=_livespec_jsonc(with_connection=False)),
        }
    )
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


def test_beads_config_without_dolt_keys_is_excluded() -> None:
    """Read, and names no dolt.* connection keys: not beads-backed, so INAPPLICABLE."""
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text="# Beads Configuration File\ndolt.mode: server\n"),
            _JSONC_ARGS: _ok(text=_livespec_jsonc()),
        }
    )
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowPass)
    assert outcome.note.startswith(EXCLUDED_NOTE_PREFIX)


def test_unparseable_livespec_jsonc_skips() -> None:
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text=_beads_config()),
            _JSONC_ARGS: _ok(text="{ this is not valid json at all ::: "),
        }
    )
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)


def test_non_object_livespec_jsonc_root_skips() -> None:
    """A `.livespec.jsonc` whose root is not an object → no connection block → skip."""
    ctx = make_context(
        table={
            _BEADS_ARGS: _ok(text=_beads_config()),
            _JSONC_ARGS: _ok(text="[1, 2, 3]\n"),
        }
    )
    outcome = assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER)
    assert isinstance(outcome, RowSkip)


def test_beads_config_ignores_lines_without_a_colon() -> None:
    """A `.beads/config.yaml` line with no `:` is skipped, not split."""
    text = (
        "# Beads Configuration File\n"
        "this-line-has-no-colon\n"
        "dolt.server-host: 127.0.0.1\n"
        "dolt.server-port: 3307\n"
        "dolt.server-user: widget\n"
        "dolt.database: widget\n"
        "dolt.prefix: widget\n"
    )
    ctx = make_context(
        table={_BEADS_ARGS: _ok(text=text), _JSONC_ARGS: _ok(text=_livespec_jsonc())}
    )
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_beads_config_strips_quoted_values() -> None:
    """Quoted YAML values compare equal to bare `.livespec.jsonc` values."""
    text = (
        'dolt.server-host: "127.0.0.1"\n'
        "dolt.server-port: 3307\n"
        "dolt.server-user: 'widget'\n"
        "dolt.database: widget\n"
        "dolt.prefix: widget\n"
    )
    ctx = make_context(
        table={_BEADS_ARGS: _ok(text=text), _JSONC_ARGS: _ok(text=_livespec_jsonc())}
    )
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_connection_found_via_generic_block_scan() -> None:
    """When no `implementation.plugin` names the block, scan for any `connection`."""
    jsonc = (
        "// no implementation.plugin pointer here\n"
        "{\n"
        '  "some-plugin": {\n'
        '    "format": "beads",\n'
        '    "connection": {\n'
        '      "prefix": "widget",\n'
        '      "database": "widget",\n'
        '      "server_user": "widget",\n'
        '      "server_host": "127.0.0.1",\n'
        '      "server_port": 3307\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config()), _JSONC_ARGS: _ok(text=jsonc)})
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_implementation_not_a_dict_falls_back_to_scan() -> None:
    """A non-dict `implementation` value is ignored; the generic scan still finds it."""
    jsonc = (
        "{\n"
        '  "implementation": "not-a-dict",\n'
        '  "some-plugin": {\n'
        '    "connection": {\n'
        '      "prefix": "widget",\n'
        '      "database": "widget",\n'
        '      "server_user": "widget",\n'
        '      "server_host": "127.0.0.1",\n'
        '      "server_port": 3307\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config()), _JSONC_ARGS: _ok(text=jsonc)})
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_implementation_plugin_not_a_string_falls_back_to_scan() -> None:
    """A non-string `implementation.plugin` is ignored; the generic scan still finds it."""
    jsonc = (
        "{\n"
        '  "implementation": { "plugin": 7 },\n'
        '  "some-plugin": {\n'
        '    "connection": {\n'
        '      "prefix": "widget",\n'
        '      "database": "widget",\n'
        '      "server_user": "widget",\n'
        '      "server_host": "127.0.0.1",\n'
        '      "server_port": 3307\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config()), _JSONC_ARGS: _ok(text=jsonc)})
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_named_plugin_block_not_a_dict_falls_back_to_scan() -> None:
    """A non-dict block at the named plugin key is ignored; the generic scan finds it."""
    jsonc = (
        "{\n"
        '  "implementation": { "plugin": "ghost-plugin" },\n'
        '  "ghost-plugin": "not-a-dict",\n'
        '  "some-plugin": {\n'
        '    "connection": {\n'
        '      "prefix": "widget",\n'
        '      "database": "widget",\n'
        '      "server_user": "widget",\n'
        '      "server_host": "127.0.0.1",\n'
        '      "server_port": 3307\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config()), _JSONC_ARGS: _ok(text=jsonc)})
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_named_plugin_block_connection_not_a_dict_falls_back_to_scan() -> None:
    """A non-dict `connection` at the named block is ignored; another block's wins."""
    jsonc = (
        "{\n"
        '  "implementation": { "plugin": "named-plugin" },\n'
        '  "named-plugin": { "connection": "not-a-dict" },\n'
        '  "some-plugin": {\n'
        '    "connection": {\n'
        '      "prefix": "widget",\n'
        '      "database": "widget",\n'
        '      "server_user": "widget",\n'
        '      "server_host": "127.0.0.1",\n'
        '      "server_port": 3307\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config()), _JSONC_ARGS: _ok(text=jsonc)})
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_non_dict_top_level_blocks_skipped_during_scan() -> None:
    """Non-dict top-level values are skipped during the generic scan."""
    jsonc = (
        "{\n"
        '  "template": "livespec",\n'
        '  "spec_root": "SPECIFICATION",\n'
        '  "some-plugin": {\n'
        '    "connection": {\n'
        '      "prefix": "widget",\n'
        '      "database": "widget",\n'
        '      "server_user": "widget",\n'
        '      "server_host": "127.0.0.1",\n'
        '      "server_port": 3307\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config()), _JSONC_ARGS: _ok(text=jsonc)})
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_block_without_connection_skipped_during_scan() -> None:
    """A dict block carrying no `connection` is passed over by the generic scan."""
    jsonc = (
        "{\n"
        '  "compat-only": { "livespec": ">=0.1.0" },\n'
        '  "some-plugin": {\n'
        '    "connection": {\n'
        '      "prefix": "widget",\n'
        '      "database": "widget",\n'
        '      "server_user": "widget",\n'
        '      "server_host": "127.0.0.1",\n'
        '      "server_port": 3307\n'
        "    }\n"
        "  }\n"
        "}\n"
    )
    ctx = make_context(table={_BEADS_ARGS: _ok(text=_beads_config()), _JSONC_ARGS: _ok(text=jsonc)})
    assert assert_tenant_connection_consistency(ctx=ctx, member=_MEMBER) == RowPass()


def test_connection_field_pairs_cover_the_five_load_bearing_fields() -> None:
    from livespec_dev_tooling.fleet._rows_beads import CONNECTION_FIELD_PAIRS

    beads_keys = {beads for beads, _ in CONNECTION_FIELD_PAIRS}
    jsonc_keys = {jsonc for _, jsonc in CONNECTION_FIELD_PAIRS}
    assert beads_keys == {
        "dolt.server-host",
        "dolt.server-port",
        "dolt.server-user",
        "dolt.database",
        "dolt.prefix",
    }
    assert jsonc_keys == {"server_host", "server_port", "server_user", "database", "prefix"}
