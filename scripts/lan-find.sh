#!/usr/bin/env bash
# lan-find.sh — locate a LAN host by MAC address (fallback for floating IPs)
#
# Usage:
#   ./lan-find.sh aa:bb:cc:dd:ee:ff              # find IP by MAC
#   ./lan-find.sh aa:bb:cc:dd:ee:ff 192.168.0    # specify subnet
#   ./lan-find.sh --list                          # list all online hosts
#
# How it works: concurrent ping the /24 → kernel ARP table fills up → match MAC
# Deps: ping (built-in). Scans a /24 in ~1-5 s.

set -uo pipefail

MAC="${1:-}"
SUBNET="${2:-192.168.0}"

if [[ -z "$MAC" ]]; then
  echo "Usage: $0 <MAC> [subnet]   e.g. $0 aa:bb:cc:dd:ee:ff 192.168.0" >&2
  echo "       $0 --list         list all online hosts" >&2
  exit 1
fi

# Concurrent ping to populate the ARP table
for i in $(seq 1 254); do
  ping -c1 -W1 "$SUBNET.$i" >/dev/null 2>&1 &
done
wait

if [[ "$MAC" == "--list" ]]; then
  printf "%-16s %s\n" "IP" "MAC"
  awk 'NR>1 && $4!="00:00:00:00:00:00" {printf "%-16s %s\n", $1, $4}' /proc/net/arp \
    | sort -t. -k4 -n
  exit 0
fi

# Normalize MAC (accepts - or : separators, case-insensitive)
norm() { echo "$1" | tr 'A-F' 'a-f' | tr '-' ':'; }
WANT=$(norm "$MAC")

FOUND=$(awk -v m="$WANT" 'NR>1 {mac=tolower($4); gsub("-",":",mac); if(mac==m) print $1}' /proc/net/arp)

if [[ -n "$FOUND" ]]; then
  echo "$FOUND"
  exit 0
else
  echo "MAC $MAC not found on $SUBNET.0/24" >&2
  exit 2
fi
