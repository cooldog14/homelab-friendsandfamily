#!/usr/bin/env bash
# Trusted escrow files are shell input; never enable tracing or print tool errors.
set +x
set -euo pipefail
umask 077

fail() { printf 'recovery-proof: %s\n' "$*" >&2; exit 1; }
[[ $# == 2 ]] || fail 'usage: recovery-proof.sh APP_ENV MALICE_ENV'
for command in restic python3 sqlite3 tar od; do
    command -v "$command" >/dev/null || fail "missing dependency: $command"
done

# Check paths and permissions before sourcing either trusted record. Resolve
# symlinks so a record stored outside git cannot point into the checkout.
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
validate_env() {
    python3 - "$1" "$repo" <<'PY'
import os
import stat
import sys
p = os.path.realpath(sys.argv[1])
s = os.stat(p)
if (not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode) != 0o600
        or s.st_uid != os.getuid()
        or os.path.commonpath([p, sys.argv[2]]) == sys.argv[2]):
    raise SystemExit(1)
print(p)
PY
}
app_env=$(validate_env "$1" 2>/dev/null) || fail 'application escrow must be owner-owned, mode 0600 and outside the repository'
malice_env=$(validate_env "$2" 2>/dev/null) || fail 'hypervisor escrow must be owner-owned, mode 0600 and outside the repository'
rt=$(mktemp -d)
trap 'rm -rf -- "$rt"' EXIT

restore_repository() (
    label=$1
    env_file=$2
    shift 2
    # Remove inherited restic/AWS configuration, including password commands,
    # so each repository depends only on its own escrow record.
    for name in ${!RESTIC_@} ${!AWS_@}; do unset "$name"; done
    set -a
    # shellcheck disable=SC1090
    source "$env_file" >"$rt/$label.env.log" 2>&1
    set +a
    for name in RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION; do
        [[ -n ${!name:-} ]] || fail "$label missing $name"
        export "${name?}"
    done
    mkdir "$rt/$label"
    restic --no-lock --no-cache snapshots --json >"$rt/$label.snapshots.json" 2>"$rt/$label.log" || fail "$label snapshot listing failed"
    snapshot=$(python3 - "$rt/$label.snapshots.json" <<'PY'
import datetime
import json
import re
import sys
with open(sys.argv[1]) as f:
    snapshots = json.load(f)
if not isinstance(snapshots, list) or not snapshots:
    raise SystemExit(1)
def timestamp(s):
    if not re.fullmatch(r'[0-9a-f]{64}', s['id']):
        raise ValueError('invalid snapshot ID')
    t = datetime.datetime.fromisoformat(s['time'].replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('missing snapshot timezone')
    return t
print(max(snapshots, key=timestamp)['id'])
PY
    ) 2>"$rt/$label.selection.log" || fail "$label has no valid snapshots"
    restic --no-lock --no-cache restore "$snapshot" --verify --target "$rt/$label" "$@" >"$rt/$label.restore.log" 2>&1 || fail "$label verified restore failed"
    printf '%s\n' "$snapshot" >"$rt/$label.id"
)

restore_repository application "$app_env" \
    --include /mnt/fast/dumps \
    --include /opt/vps-backup/Caddyfile \
    --include /opt/vps-backup/nftables.conf
restore_repository hypervisor "$malice_env" \
    --include /etc/fstab \
    --include /etc/pve/storage.cfg \
    --include /var/lib/pve-cluster/config.db

nonempty() { [[ -f $1 && -s $1 ]] || fail "missing/empty artifact: ${1##*/}"; }
sqlite_check() {
    nonempty "$1"
    local result
    result=$(sqlite3 -readonly "$1" 'PRAGMA integrity_check;' 2>"$rt/sqlite.log") || fail "SQLite check failed: ${1##*/}"
    [[ $result == ok ]] || fail "SQLite integrity failed: ${1##*/}"
}
dumps=$rt/application/mnt/fast/dumps
for name in immich.sql paperless.sql; do
    nonempty "$dumps/$name"
    python3 - "$dumps/$name" <<'PY' 2>"$rt/sql-header.log" || fail "SQL dump header missing: $name"
import sys
with open(sys.argv[1], 'rb') as f:
    if b'-- PostgreSQL database dump' not in f.read(4096).splitlines():
        raise SystemExit(1)
PY
done
for name in bazarr.db filebrowser-family.sqlite filebrowser-quantum.sqlite \
    filebrowser-upload.sqlite gotify.db grafana.db jellyfin.db jellyseerr.sqlite \
    kavita.db mumble.sqlite navidrome.db prowlarr.db radarr.db slskd-events.db \
    slskd-messaging.db slskd-search.db slskd-transfers.db sonarr.db wrtag.db; do
    sqlite_check "$dumps/$name"
done
for name in filebrowser-family.boltdb filebrowser-quantum.boltdb filebrowser-upload.boltdb; do
    nonempty "$dumps/$name"
    magic=$(od -An -tx1 -j16 -N4 "$dumps/$name" 2>"$rt/bolt.log") || fail "Bolt read failed: $name"
    [[ ${magic//[[:space:]]/} == edda0ced ]] || fail "Bolt magic invalid: $name"
done
nonempty "$dumps/suwayomi-state.tar"
tar -tf "$dumps/suwayomi-state.tar" >"$rt/tar.log" 2>&1 || fail 'Suwayomi archive invalid'
for path in application/opt/vps-backup/Caddyfile application/opt/vps-backup/nftables.conf \
    hypervisor/etc/fstab hypervisor/etc/pve/storage.cfg; do
    nonempty "$rt/$path"
done
sqlite_check "$rt/hypervisor/var/lib/pve-cluster/config.db"
printf 'application snapshot %s: PASS\n' "$(cat "$rt/application.id")"
printf 'hypervisor snapshot %s: PASS\n' "$(cat "$rt/hypervisor.id")"
printf 'Selected artifact integrity only; SQL import and Bolt application smoke remain separate.\n'
