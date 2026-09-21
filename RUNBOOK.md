# runbook

Break one thing at a time.
Use a quiet window.
Do not test by deleting data.

## public service down

Break: stop one harmless public service.
Observe: public-check fails, Gotify alerts, systemd logs show failure.
Repair: restart the stack from Dockge or docker compose.
Note: detection time and repair time.

## private caddy bad config

Break: test a bad edge Caddy config.
Observe: edge-reload must fail before restart.
Repair: restore the valid config.
Note: whether validation blocked the outage.

## backup stale

Break: simulate an old backup marker.
Observe: backup watchdog alerts Gotify.
Repair: run backup or restore the marker.
Note: alert path and delay.

## WireGuard link

Break: only with console access, stop the tunnel briefly.
Observe: public HTTP fails and make tunnel shows the issue.
Repair: restart wg-quick.
Note: user impact and recovery command.

## VPS Caddy bad config

Break: test a bad site file.
Observe: Caddy validation blocks reload.
Repair: fix the file and run make vps.
Note: what the validation caught.

## restore drill

Break: nothing in production.
Restore: one small DB dump or state file to a temp path.
Verify: file readable or DB integrity ok.
Note: RTO, RPO, and exact commands.

## incident 2026-09-20: jellyfin disk full, then green glitch

Incident: chill-01 (VM 101) root disk filled to 100% mid-film (F1 4K remux,
family movie night); after recovery the next film (Ford v Ferrari 4K remux)
showed green glitch everywhere on the Tizen TV app.
Impact: film 1 stalled (ffmpeg exit 228, 0-byte HLS playlist/segments, 80x
SQLite Error 13, 1354x rollback cascade, resume not saving); container stayed
healthy, no data loss. Film 2 unwatchable with PGS subtitles (silent frame
corruption, encoder log clean at ~2x speed).
Detection: user report during playback. `docker logs` showed `No space left
on device` on ffmpeg log writes; `df` showed 100%/0 free; `du` found a 26G
single-session HLS cache + 42G docker images on the 80G root disk.
Thought process: the rollback/SQLite errors looked like DB corruption at
first, but `database or disk is full` + ffmpeg ENOSPC pointed at disk, not
the DB. For the green glitch, a clean encode log + `overlay_qsv` subtitle
burn-in stage in the ffmpeg chain pointed at silent filter corruption;
isolation proposed via subs-off toggle on the TV.
Repair (live, no pauses): builder prune (2.8G) + orphan-image removal only
(never running images, never the active session) -> 13G free, ENOSPC gone.
Post-film: encoding.xml set HEVC HW decode on, throttling on, segment
deletion on/keep 120s; jellyfin restarted clean (0 errors); h264_qsv encode
+ hevc_qsv decode smoke-tested on the real file. Decision qsv->vaapi pending:
same iHD driver/silicon (QSV on Linux wraps VAAPI), same speed/quality, and
overlay_vaapi avoids the green-frame bug; UHD 630 has no QSV-only features
worth keeping.
Repair time: ~1h alongside playback; tuning ~15 min post-film.
Prevention: jellyfin-cache moved to /mnt/fast/jellyfin-cache in git
2026-09-21; still add >85% / Gotify alert and weekly builder/image prune.
Lesson: check disk before blaming the database; filter-stage corruption logs
nothing, so isolate with client-side toggles first.

## incident note

Incident:
Impact:
Detection:
Repair:
Repair time:
Prevention:
