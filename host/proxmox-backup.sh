#!/bin/sh
# Monthly Proxmox second-copy backup (audit 2026-09-12).
# RUNS ON malice (the Proxmox host), not on a guest. Restic stays primary;
# this is the hypervisor-level copy so a dead restic repo isn't the end.
# Install: copy to /usr/local/sbin/proxmox-backup on malice, then:
#   echo '17 3 1 * * root /usr/local/sbin/proxmox-backup' > /etc/cron.d/proxmox-backup
# Guests: 101 chill-01. Mode snapshot = no downtime.
# Keeps the 2 newest archives per guest on the `backup` storage (/mnt/backup).
set -eu
log() { printf '[%s] %s\n' "$(date -Is)" "$*"; }
DUMP_DIR=/mnt/backup/dump
vmid=101
log "vzdump $vmid start"
if vzdump "$vmid" --storage backup --mode snapshot --compress zstd; then
  log "vzdump $vmid ok"
else
  log "vzdump $vmid FAILED"
fi
find "$DUMP_DIR" -maxdepth 1 -name "vzdump-qemu-$vmid-*" -printf '%T@ %p\n' 2>/dev/null \
  | sort -rn | tail -n +3 | cut -d' ' -f2- | while read -r old; do
    log "prune $old"
    rm -f "$old"
  done
log "done"
