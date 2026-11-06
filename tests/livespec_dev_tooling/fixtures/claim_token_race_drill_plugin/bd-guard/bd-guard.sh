#!/bin/sh
# Stand-in for the released lifecycle guard: delegates to LIVESPEC_BD_REAL.
exec "${LIVESPEC_BD_REAL:?}" "$@"
