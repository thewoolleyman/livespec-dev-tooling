#!/usr/bin/env bash
# Severity levers shared by every `just check` surface in this repository.
# Keep these names equal to the LIVESPEC_FAIL_IF_* entries in ci.yml; the
# check-ci-matrix-completeness aggregate member enforces that parity.
export LIVESPEC_FAIL_IF_CI_GATE_PARITY_GAPS_EXIST=true
export LIVESPEC_FAIL_IF_CI_MATRIX_GAPS_EXIST=true
export LIVESPEC_FAIL_IF_FMT_DIRECTIVES_EXIST=true
