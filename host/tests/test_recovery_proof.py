"""Isolated artifact/cleanup tests; not evidence of an offsite restore."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'recovery-proof.sh'
SQLITE_NAMES = '''bazarr.db filebrowser-family.sqlite filebrowser-quantum.sqlite
filebrowser-upload.sqlite gotify.db grafana.db jellyfin.db jellyseerr.sqlite
kavita.db mumble.sqlite navidrome.db prowlarr.db radarr.db slskd-events.db
slskd-messaging.db slskd-search.db slskd-transfers.db sonarr.db wrtag.db'''.split()


class RecoveryProof(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.scratch = self.root / 'scratch'
        self.scratch.mkdir()
        (self.scratch / 'unrelated').write_text('keep')
        self.fixtures = self.root / 'fixtures'
        self.dumps = self.fixtures / 'application/mnt/fast/dumps'
        self.dumps.mkdir(parents=True)
        for name in ['immich.sql', 'paperless.sql']:
            (self.dumps / name).write_text('-- PostgreSQL database dump\n')
        for name in SQLITE_NAMES:
            with closing(sqlite3.connect(self.dumps / name)) as db:
                db.execute('create table proof (id integer)')
        for name in ['family', 'quantum', 'upload']:
            (self.dumps / f'filebrowser-{name}.boltdb').write_bytes(bytes(16) + bytes.fromhex('edda0ced'))
        with tarfile.open(self.dumps / 'suwayomi-state.tar', 'w'):
            pass
        for path in ['application/opt/vps-backup/Caddyfile', 'application/opt/vps-backup/nftables.conf',
                     'hypervisor/etc/fstab', 'hypervisor/etc/pve/storage.cfg']:
            p = self.fixtures / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture\n')
        db_path = self.fixtures / 'hypervisor/var/lib/pve-cluster/config.db'
        db_path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(db_path)) as db:
            db.execute('create table proof (id integer)')
        self.executable('sqlite3', '''from contextlib import closing
import sqlite3, sys
try:
    with closing(sqlite3.connect('file:' + sys.argv[2] + '?mode=ro', uri=True)) as db:
        print('\\n'.join(row[0] for row in db.execute(sys.argv[3])))
except sqlite3.Error:
    raise SystemExit(1)
''')
        self.executable('restic', '''import json, os, pathlib, shutil, sys
args = sys.argv[1:]
assert args[:2] == ['--no-lock', '--no-cache']
repo = os.environ['RESTIC_REPOSITORY']
assert os.environ['AWS_DEFAULT_REGION'] == repo
assert 'RESTIC_PASSWORD_COMMAND' not in os.environ
if args[2] == 'snapshots':
    assert args[3:] == ['--json']
    print('[]' if os.environ.get('EMPTY_REPO') else json.dumps([
        {'id': 'a'*64, 'time': '2026-01-01T00:00:00Z'},
        {'id': 'b'*64, 'time': '2026-02-01T00:00:00Z'}]))
elif args[2] == 'restore':
    assert args[3] == 'b'*64 and '--verify' in args
    assert args.count('--include') == 3
    assert not any('wireguard' in a for a in args)
    if os.environ.get('RESTORE_FAIL'):
        print('secret-canary', file=sys.stderr)
        raise SystemExit(1)
    target = pathlib.Path(args[args.index('--target')+1])
    shutil.copytree(pathlib.Path(os.environ['FIXTURES']) / repo, target, dirs_exist_ok=True)
else:
    raise AssertionError(args)
''')
        self.envs = []
        for repo in ['application', 'hypervisor']:
            p = self.root / (repo + '.env')
            p.write_text(f'RESTIC_REPOSITORY={repo}\nRESTIC_PASSWORD=fixture\nAWS_ACCESS_KEY_ID=fixture\nAWS_SECRET_ACCESS_KEY=fixture\nAWS_DEFAULT_REGION={repo}\n')
            p.chmod(0o600)
            self.envs.append(p)

    def executable(self, name, code):
        p = self.bin / name
        p.write_text('#!/usr/bin/env python3\n' + code)
        p.chmod(0o700)

    def run_proof(self, **extra):
        env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                   TMPDIR=str(self.scratch), FIXTURES=str(self.fixtures),
                   RESTIC_PASSWORD_COMMAND='must-not-run', **extra)
        result = subprocess.run(['bash', str(SCRIPT), *map(str, self.envs)],
                                env=env, capture_output=True, text=True)
        self.assertEqual([p.name for p in self.scratch.iterdir()], ['unrelated'])
        self.assertNotIn('secret-canary', result.stdout + result.stderr)
        return result

    def test_valid_and_repository_isolation(self):
        result = self.run_proof()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('application snapshot ' + 'b'*64 + ': PASS', result.stdout)
        self.assertIn('hypervisor snapshot ' + 'b'*64 + ': PASS', result.stdout)

    def test_empty_repository(self):
        self.assertNotEqual(self.run_proof(EMPTY_REPO='1').returncode, 0)

    def test_missing_required_artifact_despite_extra_database(self):
        (self.dumps / 'sonarr.db').rename(self.dumps / 'unrelated.db')
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_corrupt_sqlite(self):
        (self.dumps / 'radarr.db').write_bytes(b'not sqlite')
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_restore_failure_is_private(self):
        self.assertNotEqual(self.run_proof(RESTORE_FAIL='1').returncode, 0)

    def test_missing_credential_does_not_inherit(self):
        self.envs[1].write_text('RESTIC_REPOSITORY=hypervisor\n')
        self.assertNotEqual(self.run_proof().returncode, 0)

    def test_escrow_permissions(self):
        self.envs[0].chmod(0o644)
        self.assertNotEqual(self.run_proof().returncode, 0)


if __name__ == '__main__':
    unittest.main()
