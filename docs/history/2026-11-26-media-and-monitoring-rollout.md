# Media and monitoring rollout — 2026-11-26

At 16:52 CET, make deploy shipped main commit 9811c2159b to chill-01.
The previous deployed commit was 3a46e1291c. CI and make check passed.
Music Manager stayed on a separate branch and had no live service or route.

## Verified live

- Jellyfin's music, movie, and TV libraries use read-only mounts. Playback
  returned data for one item from each library. No media was moved.
- Bazarr authenticated with the dashboard key. Jellyfin served movie and TV
  subtitles; Bazarr could read them and had write access to their directories.
- All 44 stack containers were running. Caddy's local health check passed,
  and the dashboard reached Navidrome on the private Docker network.
- Prometheus collected six healthy app checks and both Arr queues. All 43
  alert rules loaded. The download scan was fresh and found no executables.
  The OOM counters were present. Sonarr had nine imports under watch; the
  24-hour alert had not fired.
- All 14 public, 16 private, and four TCP probes passed. All four local alert
  components reported healthy, and the public health bit was true. This was
  not a notification delivery drill.

## Still held

Only the Jellyfin and Bazarr mount batch went live. Follow the
[mount rollout order](../../RUNBOOK.md#mount-narrowing-rollout) for the rest.
Filebrowser was not restarted. It still uses the
[default of not trusting proxy headers](https://filebrowserquantum.com/en/docs/configuration/http/#trustproxyheaders-v200--trustedheaders-v14xv15x),
which is now explicit in the config on disk. The WAN Worker was not deployed.

## Alert wording

Commit ca861555d4 put Prometheus alert messages and the Grafana overview in
English. The live dashboard showed Sonarr imports as pending, with 24 hours
stated as the condition for firing. The swap test showed 0.017 pages per
second instead of zero. Alert thresholds and mounts did not change.
