# todo

## next

- Deploy current repo.
- Add minimal GitOps with systemd.
- Add public exposure guard.
- Run one restore drill.
- Write short incident samples.

## storage layout

- 4TB HDD: movies, TV, downloads, disposable media.
- 2TB HDD: important data, photos, documents, clean music, app data.
- 1TB HDD: local critical backup or Restic copy.
- SSD 1: Proxmox and VM disks.
- SSD 2: fast data, cache, DB dumps, transcodes, staging.

Do not add RAID or ZFS complexity until matching disks exist.
