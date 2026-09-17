#!/bin/sh
set -eu

if [ "${1:-}" = "--self-check" ]; then
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  mkdir -p "$tmp/bin"
  cat > "$tmp/bin/df" <<'SH'
#!/bin/sh
cat <<'DF'
Mounted on 1B-blocks Used Use%
/ 100 25 25%
/mnt/data 200 150 75%
DF
SH
  chmod +x "$tmp/bin/df"
  PATH="$tmp/bin:$PATH" "$0" "$tmp/disks.json"
  grep -q '"mount":"/"' "$tmp/disks.json"
  grep -q '"mount":"/mnt/data"' "$tmp/disks.json"
  grep -q '"percent":75' "$tmp/disks.json"
  echo "disk usage self-check ok"
  exit 0
fi

out=${1:-/opt/stacks/edge/state/home/disks.json}
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
mkdir -p "$(dirname "$out")"

{
  printf '{"updated":"%s","disks":[' "$(date -Is)"
  df -B1 --output=target,size,used,pcent -x tmpfs -x devtmpfs -x squashfs -x overlay |
    awk '
      NR > 1 {
        pct = $4
        sub(/%/, "", pct)
        gsub(/\\/, "\\\\", $1)
        gsub(/"/, "\\\"", $1)
        printf "%s{\"mount\":\"%s\",\"size\":%s,\"used\":%s,\"percent\":%s}", sep, $1, $2, $3, pct
        sep = ","
      }
    '
  printf ']}'
} > "$tmp"

install -m 644 "$tmp" "$out"
