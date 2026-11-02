#!/bin/sh
case "$*" in
  *'--dry-run=client'*)
    cat
    exit 0 ;;
  'apply -f -')
    if mkdir "${RBAC_APPLY_LOCK}" 2>/dev/null; then
      holder=yes
    else
      holder=no
      printf 'overlap\n' >> "${RBAC_APPLY_LOG}"
    fi
    cat > "${RBAC_APPLY_CAPTURES}/manifest.$$"
    printf 'enter %s\n' "$$" >> "${RBAC_APPLY_LOG}"
    if [ "${RBAC_APPLY_RENDEZVOUS:-}" = enabled ]; then
      : > "${RBAC_APPLY_ENTERS}/$$"
      deadline=$(( $(date +%s) + RBAC_APPLY_RENDEZVOUS_TIMEOUT_SECONDS ))
      while :; do
        set -- "${RBAC_APPLY_ENTERS}"/*
        if [ "$#" -ge 2 ]; then
          break
        fi
        if [ "$(date +%s)" -ge "$deadline" ]; then
          printf 'two unserialized applies were never in flight together\n' >&2
          printf 'leave %s\n' "$$" >> "${RBAC_APPLY_LOG}"
          if [ "${holder}" = yes ]; then
            rmdir "${RBAC_APPLY_LOCK}"
          fi
          exit 1
        fi
        sleep 0.05
      done
    fi
    printf 'leave %s\n' "$$" >> "${RBAC_APPLY_LOG}"
    if [ "${holder}" = yes ]; then
      rmdir "${RBAC_APPLY_LOCK}"
    fi
    printf 'namespace/%s configured\n' "${RBAC_APPLY_NAMESPACE}"
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\n' "$*" >&2
exit 1
