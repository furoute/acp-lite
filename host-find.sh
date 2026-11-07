#!/usr/bin/env bash
# host-find.sh — locate a DHCP host by hostname over SSH
#
# Sibling of lan-find.sh. Use lan-find.sh when you know the MAC (one /24 in 1-5 s,
# pure ARP). Use this one when you know the hostname but not the MAC -- or when the
# host is on a subnet your ARP table cannot see.
#
# Usage:
#   ./host-find.sh <hostname>                       # default subnets
#   ./host-find.sh <hostname> <user>                # + SSH user
#   ./host-find.sh <hostname> <user> 192.168.0 10.196.0   # + subnets
#
# Env:
#   HOST_FIND_CACHE=1   cache the answer under ${XDG_CACHE_HOME:-$HOME/.cache}/host-find/
#   HOST_FIND_PORT=22   port to probe (only useful for testing the sensor itself)
#
# How it works: probe port 22 concurrently, then run `ssh ... hostname` against
# every open port and compare. Slower than ARP but works across subnets and
# survives Wi-Fi MAC randomization.
#
# Deps: ssh, bash. A /24 takes roughly 2-11 s depending on how many hosts run sshd.

set -uo pipefail

HOST="${1:-}"
USER_NAME="${2:-${USER:-}}"

if [[ -z "$HOST" ]]; then
  echo "Usage: $0 <hostname> [user] [subnet ...]" >&2
  exit 1
fi

ARGS=("$@")
SUBNETS=()
if [[ ${#ARGS[@]} -gt 2 ]]; then
  SUBNETS=("${ARGS[@]:2}")
fi
if [[ ${#SUBNETS[@]} -eq 0 ]]; then
  SUBNETS=(192.168.0 192.168.1 10.0.0)
fi

CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/host-find"
CACHE_FILE="$CACHE_DIR/$HOST"
WANT=$(echo "$HOST" | tr 'A-Z' 'a-z')

# ---- cache hit -------------------------------------------------------------
if [[ "${HOST_FIND_CACHE:-0}" == "1" && -f "$CACHE_FILE" ]]; then
  CACHED=$(cat "$CACHE_FILE")
  GOT=$(ssh -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=accept-new \
          "${USER_NAME:+$USER_NAME@}$CACHED" hostname 2>/dev/null | tr 'A-Z' 'a-z' | tr -d '\r')
  if [[ "$GOT" == "$WANT" ]]; then
    echo "$CACHED"
    exit 0
  fi
fi

# ---- probe port 22 on every address ---------------------------------------
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

for net in "${SUBNETS[@]}"; do
  for i in $(seq 1 254); do
    ip="$net.$i"
    ( timeout 1 bash -c "echo > /dev/tcp/$ip/${HOST_FIND_PORT:-22}" 2>/dev/null && echo "$ip" >> "$TMP" ) &
    while (( $(jobs -rp | wc -l) >= 128 )); do wait -n 2>/dev/null || break; done
  done
done
wait
sort -u -o "$TMP" "$TMP"

COUNT=$(wc -l < "$TMP")
if [[ "$COUNT" -eq 0 ]]; then
  echo "No host answered on port 22 in: ${SUBNETS[*]}" >&2
  exit 2
fi

# ---- identify by hostname -------------------------------------------------
while IFS= read -r ip; do
  [[ -z "$ip" ]] && continue
  GOT=$(ssh -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=accept-new \
          "${USER_NAME:+$USER_NAME@}$ip" hostname 2>/dev/null | tr 'A-Z' 'a-z' | tr -d '\r')
  if [[ "$GOT" == "$WANT" ]]; then
    if [[ "${HOST_FIND_CACHE:-0}" == "1" ]]; then
      mkdir -p "$CACHE_DIR" && echo "$ip" > "$CACHE_FILE"
    fi
    echo "$ip"
    exit 0
  fi
done < "$TMP"

echo "Host '$HOST' not found among $COUNT SSH hosts in: ${SUBNETS[*]}" >&2
exit 3
