# tests/livespec_dev_tooling/checks/

Mirrors `livespec_dev_tooling/checks/` one-to-one — one
`test_<slug>.py` per check module. Each test exercises the
check's main path (pass + fail trees) via the structlog JSON
finding stream the check emits to stderr.
