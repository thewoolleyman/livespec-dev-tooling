---
name: hello
description: A no-op fixture skill that exists solely to exercise structural skill discovery in the CLI e2e harness self-test. Not a real plugin skill.
allowed-tools: Write
---

# hello

This SKILL.md exists only so the harness's structural discovery walk finds
exactly one skill (`hello`) under this fixture-plugin. The harness self-test
pairs it with the `e2e-cli-fixtures/hello/` fixture and a fake `claude` runner
that materializes the expected output file — proving discovery, the time-bomb
coverage gate, and a fixture round-trip work in isolation.
