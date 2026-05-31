# tests/livespec_dev_tooling/testing/

Mirror-paired tests for `livespec_dev_tooling/testing/`. `test_cli_e2e.py`
exercises the CLI e2e harness end-to-end WITHOUT a real `claude` binary or
API key, via a deterministic injected `CliRunner`.

`fixtures/single_skill_plugin/` is the committed tiny single-skill
fixture-plugin the self-test drives: a `plugin.json` (slash prefix
`fixture-plugin`), one `skills/hello/SKILL.md`, and a matching
`e2e-cli-fixtures/hello/` fixture. It proves discovery + the time-bomb
coverage gate + a fixture round-trip work in isolation. The `fixtures/` tree
holds NO `.py`, so the mirror-pairing and coverage gates do not extend to it.
