#!/usr/bin/env bash
# approve-serving-csr.sh <host> — the operator's check-then-approve step for a
# homelab worker's kubelet SERVING certificate.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Standard bootstrap under an admission hold". Design:
# plan/homelab-k8s-worker-nodes/research/005 §3 "Serving CSR approval".
#
# No built-in approver signs kubernetes.io/kubelet-serving, and a worker is
# never given CSR-approve rights, so each serving CSR is approved here, from
# the operator's admin kubeconfig. A pending CSR is approved only when ALL of
# these hold, and is otherwise named with the reason it was refused:
#
#   - signer kubernetes.io/kubelet-serving, requested by system:node:<worker>;
#   - subject CN system:node:<worker>, O system:nodes;
#   - usages within {digital signature, key encipherment} and including
#     server auth;
#   - DNS SANs within {<worker>, <worker>.<tailnet domain>} and including
#     <worker>;
#   - IP SANs non-empty and each one an InternalIP of Node <worker>.
#
# TAILNET_DOMAIN (default perch-rudd.ts.net) names the tailnet's MagicDNS
# suffix. It exits non-zero when any CSR was refused.
set -euo pipefail

prog="approve-serving-csr"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$here/../hosts}"
domain="${TAILNET_DOMAIN:-perch-rudd.ts.net}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

say() {
  printf '%s: %s\n' "$prog" "$*"
}

[ "$#" -eq 1 ] || die "usage: $prog <host>"
host="$1"
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
worker="$host-homelab-worker"
user="system:node:$worker"

lookup_err="$(mktemp)"
trap 'rm -f "$lookup_err"' EXIT
if ! node_ips="$(kubectl get node "$worker" -o jsonpath='{range .status.addresses[?(@.type=="InternalIP")]}{.address}{"\n"}{end}' 2>"$lookup_err")"; then
  if grep -q 'NotFound' "$lookup_err"; then
    die "Node $worker is not registered; a serving CSR is approved only for a registered Node"
  fi
  die "could not read Node $worker: $(tr '\n' ' ' <"$lookup_err")"
fi
[ -n "$node_ips" ] || die "Node $worker reports no InternalIP"

# in_list <item> <newline-separated list>
in_list() {
  grep -qxF -- "$1" <<<"$2"
}

pending="$(kubectl get csr -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.signerName}{"\t"}{.spec.username}{"\t"}{.status.conditions[*].type}{"\n"}{end}' |
  awk -F'\t' -v user="$user" '$2 == "kubernetes.io/kubelet-serving" && $3 == user && $4 == "" {print $1}')"
if [ -z "$pending" ]; then
  say "no pending kubelet-serving CSR from $user"
  exit 0
fi

refused=0
refuse() {
  printf '%s: REFUSED %s: %s\n' "$prog" "$1" "$2" >&2
  refused=1
}

for csr in $pending; do
  usages="$(kubectl get csr "$csr" -o jsonpath='{range .spec.usages[*]}{@}{"\n"}{end}')"
  if ! in_list "server auth" "$usages"; then
    refuse "$csr" "usages do not include server auth"
    continue
  fi
  bad_usage=""
  while IFS= read -r usage; do
    [ -n "$usage" ] || continue
    case "$usage" in
      "digital signature" | "key encipherment" | "server auth") ;;
      *) bad_usage="$usage" ;;
    esac
  done <<EOF_USAGES
$usages
EOF_USAGES
  if [ -n "$bad_usage" ]; then
    refuse "$csr" "usage '$bad_usage' is not allowed for a serving certificate"
    continue
  fi

  text="$(kubectl get csr "$csr" -o jsonpath='{.spec.request}' | base64 -d | openssl req -noout -text 2>/dev/null)" || {
    refuse "$csr" "request is not a readable PKCS#10 CSR"
    continue
  }
  subject="$(printf '%s\n' "$text" | sed -n 's/^ *Subject: *//p' | tr -d ' ')"
  case ",$subject," in
    *",CN=$user,"*) ;;
    *)
      refuse "$csr" "subject '$subject' is not CN=$user"
      continue
      ;;
  esac
  case ",$subject," in
    *",O=system:nodes,"*) ;;
    *)
      refuse "$csr" "subject '$subject' is not in O=system:nodes"
      continue
      ;;
  esac

  sans="$(printf '%s\n' "$text" | grep -A1 'Subject Alternative Name' | tail -n 1 | tr ',' '\n' | sed 's/^ *//')"
  dns="$(printf '%s\n' "$sans" | sed -n 's/^DNS://p')"
  ips="$(printf '%s\n' "$sans" | sed -n 's/^IP Address://p')"
  other="$(printf '%s\n' "$sans" | grep -v -e '^DNS:' -e '^IP Address:' -e '^$' || true)"
  if [ -n "$other" ]; then
    refuse "$csr" "SAN '$other' is neither a DNS name nor an IP address"
    continue
  fi
  if ! in_list "$worker" "$dns"; then
    refuse "$csr" "DNS SANs do not include $worker"
    continue
  fi
  bad=""
  for name in $dns; do
    [ "$name" = "$worker" ] || [ "$name" = "$worker.$domain" ] || bad="$name"
  done
  if [ -n "$bad" ]; then
    refuse "$csr" "DNS SAN $bad is not $worker or $worker.$domain"
    continue
  fi
  if [ -z "$ips" ]; then
    refuse "$csr" "no IP SAN"
    continue
  fi
  bad=""
  for ip in $ips; do
    in_list "$ip" "$node_ips" || bad="$ip"
  done
  if [ -n "$bad" ]; then
    refuse "$csr" "IP SAN $bad is not an InternalIP of Node $worker"
    continue
  fi

  kubectl certificate approve "$csr" >/dev/null
  say "approved $csr for $worker (DNS $(printf '%s' "$dns" | tr '\n' ' ')IP $(printf '%s' "$ips" | tr '\n' ' '))"
done

[ "$refused" -eq 0 ] || exit 1
