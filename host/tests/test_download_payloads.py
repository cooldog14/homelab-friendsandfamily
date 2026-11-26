"""Isolated scanner fixtures; never scan production directories or run payloads."""

import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / 'download-payloads.py'
SPEC = importlib.util.spec_from_file_location('download_payloads', SCRIPT)
payloads = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = payloads
SPEC.loader.exec_module(payloads)


class DownloadPayloads(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'downloads'
        self.root.mkdir()
        self.metrics = self.base / 'textfile'
        self.log = io.StringIO()

    def scan(self, *roots):
        return payloads.scan(tuple(roots) or (self.root,), self.log)

    def events(self):
        return [json.loads(line) for line in self.log.getvalue().splitlines()]

    def test_every_case_insensitive_suffix(self):
        suffixes = ('.exe', '.dll', '.com', '.scr', '.msi', '.bat', '.cmd',
                    '.ps1', '.vbs', '.js', '.jar', '.sh', '.appimage')
        for suffix in suffixes:
            (self.root / ('payload' + suffix.upper())).write_bytes(b'plain text')
        result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, len(suffixes))
        self.assertEqual({event['classification'][0] for event in self.events()},
                         {'suffix:' + suffix for suffix in suffixes})

    def test_all_header_signatures_without_executable_suffixes(self):
        signatures = {
            'elf': b'\x7fELF', 'pe': b'MZ',
            'macho32be': b'\xfe\xed\xfa\xce',
            'macho32le': b'\xce\xfa\xed\xfe',
            'macho64be': b'\xfe\xed\xfa\xcf',
            'macho64le': b'\xcf\xfa\xed\xfe',
            'fat32be': b'\xca\xfe\xba\xbe',
            'fat32le': b'\xbe\xba\xfe\xca',
            'fat64be': b'\xca\xfe\xba\xbf',
            'fat64le': b'\xbf\xba\xfe\xca',
        }
        for name, header in signatures.items():
            (self.root / (name + '.bin')).write_bytes(header + b'not executed')
        result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, len(signatures))
        self.assertEqual({event['classification'][0] for event in self.events()},
                         {'header:ELF', 'header:MZ', 'header:Mach-O'})

    def test_suffix_and_header_count_one_file(self):
        (self.root / 'both.EXE').write_bytes(b'MZfixture')
        self.assertEqual(self.scan().executable_files, 1)
        self.assertEqual(self.events()[0]['classification'], ['suffix:.exe', 'header:MZ'])

    def test_archives_are_not_opened_or_extracted(self):
        with zipfile.ZipFile(self.root / 'archive.zip', 'w') as archive:
            archive.writestr('inside.exe', b'MZmust not be inspected')
        for name, header in [('archive.tar', b'ustar'), ('archive.gz', b'\x1f\x8b'),
                             ('archive.7z', b'7z\xbc\xaf'), ('archive.rar', b'Rar!')]:
            (self.root / name).write_bytes(header)
        result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 0)
        self.assertFalse((self.root / 'inside.exe').exists())
        self.assertEqual(self.events(), [])

    def test_empty_short_and_benign_files(self):
        for index, content in enumerate([b'', b'M', b'\x7fEL', b'ordinary text']):
            (self.root / f'benign-{index}.txt').write_bytes(content)
        (self.root / 'not.exe.txt').write_bytes(b'data')
        result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 0)

    def test_symlink_files_directories_and_loops_are_skipped(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'payload.exe').write_bytes(b'MZ')
        (self.root / 'file.exe').symlink_to(outside / 'payload.exe')
        (self.root / 'directory').symlink_to(outside, target_is_directory=True)
        (self.root / 'loop').symlink_to(self.root, target_is_directory=True)
        (self.root / 'dangling.exe').symlink_to(outside / 'absent')
        result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 0)

    def test_symlink_root_is_unsuccessful(self):
        linked = self.base / 'linked'
        linked.symlink_to(self.root, target_is_directory=True)
        self.assertFalse(self.scan(linked).success)

    def test_symlink_ancestor_of_root_is_not_followed(self):
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'payload.exe').write_bytes(b'MZ')
        linked = self.base / 'linked'
        linked.symlink_to(self.root, target_is_directory=True)
        result = self.scan(linked / 'nested')
        self.assertFalse(result.success)
        self.assertEqual(result.executable_files, 0)

    def test_nonregular_files_are_not_opened(self):
        os.mkfifo(self.root / 'pipe.exe')
        result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 0)

    def test_overlapping_roots_and_hardlinks_are_counted_once(self):
        nested = self.root / 'nested'
        nested.mkdir()
        original = nested / 'payload.exe'
        original.write_bytes(b'MZ')
        os.link(original, self.root / 'alias.exe')
        result = self.scan(self.root, nested, self.root)
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 1)
        self.assertEqual(len(self.events()), 1)

    def test_executable_suffix_on_later_hardlink_is_not_missed(self):
        # Separate roots give deterministic visitation order, independent of readdir.
        other = self.base / 'other'
        other.mkdir()
        benign_name = self.root / 'ordinary.txt'
        benign_name.write_bytes(b'plain text')
        os.link(benign_name, other / 'payload.exe')
        result = self.scan(self.root, other)
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 1)

    def test_paths_are_escaped_and_contents_not_logged(self):
        name = 'line\n\t"\\\x1b.exe'
        path = self.root / name
        path.write_bytes(b'secret contents must not be logged')
        self.assertEqual(self.scan().executable_files, 1)
        self.assertEqual(len(self.log.getvalue().splitlines()), 1)
        self.assertNotIn('\x1b', self.log.getvalue())
        self.assertNotIn('secret contents', self.log.getvalue())
        self.assertEqual(self.events()[0]['path'], str(path))

    def test_vanished_file_is_ignored(self):
        disappearing = self.root / 'vanishing.exe'
        disappearing.write_bytes(b'MZ')
        real_open = os.open

        def vanish(path, flags, *args, **kwargs):
            if path == disappearing.name:
                disappearing.unlink()
            return real_open(path, flags, *args, **kwargs)

        with patch.object(payloads.os, 'open', side_effect=vanish):
            result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 0)
        self.assertEqual(self.events(), [])

    def test_file_replaced_by_symlink_is_not_followed(self):
        path = self.root / 'racing.exe'
        path.write_bytes(b'MZ')
        outside = self.base / 'outside.exe'
        outside.write_bytes(b'MZ')
        real_open = os.open

        def replace(name, flags, *args, **kwargs):
            if name == path.name:
                path.unlink()
                path.symlink_to(outside)
            return real_open(name, flags, *args, **kwargs)

        with patch.object(payloads.os, 'open', side_effect=replace):
            result = self.scan()
        self.assertTrue(result.success)
        self.assertEqual(result.executable_files, 0)

    def test_directory_replaced_by_symlink_is_not_followed(self):
        path = self.root / 'nested'
        path.mkdir()
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'payload.exe').write_bytes(b'MZ')
        real_open = os.open

        def replace(name, flags, *args, **kwargs):
            if name == path.name:
                path.rmdir()
                path.symlink_to(outside, target_is_directory=True)
            return real_open(name, flags, *args, **kwargs)

        with patch.object(payloads.os, 'open', side_effect=replace):
            result = self.scan()
        self.assertEqual(result.executable_files, 0)
        # Linux returns ENOTDIR for O_NOFOLLOW | O_DIRECTORY: never claim that
        # changed tree was completely scanned, but never traverse it either.
        self.assertFalse(result.success)

    def test_missing_root_fails_even_with_other_valid_roots(self):
        (self.root / 'payload.exe').write_bytes(b'MZ')
        result = self.scan(self.root, self.base / 'missing')
        self.assertFalse(result.success)
        self.assertEqual(result.executable_files, 1)
        self.assertEqual(self.events()[-1]['errno'], errno.ENOENT)

    def test_nondirectory_root_fails(self):
        not_directory = self.base / 'file'
        not_directory.write_bytes(b'')
        self.assertFalse(self.scan(not_directory).success)

    def test_permission_denied_is_unsuccessful_independent_of_test_user(self):
        (self.root / 'unreadable.exe').write_bytes(b'MZ')
        real_open = os.open

        def deny(path, flags, *args, **kwargs):
            if path == 'unreadable.exe':
                raise PermissionError(errno.EACCES, 'private detail must not be logged')
            return real_open(path, flags, *args, **kwargs)

        with patch.object(payloads.os, 'open', side_effect=deny):
            result = self.scan()
        self.assertFalse(result.success)
        self.assertEqual(self.events()[0]['errno'], errno.EACCES)
        self.assertNotIn('private detail', self.log.getvalue())

    def test_header_read_io_failure_is_unsuccessful(self):
        (self.root / 'broken.exe').write_bytes(b'MZ')
        with patch.object(payloads.os, 'read', side_effect=OSError(errno.EIO, 'fixture')):
            result = self.scan()
        self.assertFalse(result.success)
        self.assertEqual(self.events()[0]['errno'], errno.EIO)

    def test_directory_enumeration_failure_is_unsuccessful(self):
        with patch.object(payloads.os, 'scandir', side_effect=PermissionError(errno.EACCES, 'fixture')):
            result = self.scan()
        self.assertFalse(result.success)
        self.assertEqual(self.events()[0]['errno'], errno.EACCES)

    def test_directory_iteration_io_failure_is_unsuccessful(self):
        class BrokenIterator:
            def __next__(self):
                raise OSError(errno.EIO, 'fixture')

            def close(self):
                pass

        with patch.object(payloads.os, 'scandir', return_value=BrokenIterator()):
            result = self.scan()
        self.assertFalse(result.success)
        self.assertEqual(self.events()[0]['errno'], errno.EIO)

    def test_success_metrics_include_zero_and_timestamp_without_labels(self):
        metrics = payloads.render_metrics(payloads.ScanResult(0, True), 1234)
        self.assertIn('\nhomelab_download_executable_files 0\n', metrics)
        self.assertIn('\nhomelab_download_payload_scan_success 1\n', metrics)
        self.assertIn('\nhomelab_download_payload_scan_timestamp_seconds 1234\n', metrics)
        self.assertNotIn('{', metrics)
        self.assertNotIn(str(self.root), metrics)

    def test_failed_metrics_omit_count_even_if_partial_findings_exist(self):
        for count in [0, 3]:
            with self.subTest(count=count):
                metrics = payloads.render_metrics(payloads.ScanResult(count, False), 1234)
                samples = [line for line in metrics.splitlines() if not line.startswith('#')]
                self.assertFalse(any(line.startswith('homelab_download_executable_files ')
                                     for line in samples))
                self.assertIn('homelab_download_payload_scan_success 0', samples)
                self.assertIn('homelab_download_payload_scan_timestamp_seconds 1234', samples)

    def test_atomic_metrics_replace_and_cleanup(self):
        payloads.write_metrics(self.metrics, 'old\n')
        target = self.metrics / payloads.OUTPUT
        real_replace = os.replace
        observed = []

        def inspect(source, destination):
            observed.append(Path(source).read_text())
            self.assertEqual(target.read_text(), 'old\n')
            self.assertNotEqual(Path(source).suffix, '.prom')
            real_replace(source, destination)

        with patch.object(payloads.os, 'replace', side_effect=inspect):
            payloads.write_metrics(self.metrics, 'complete\n')
        self.assertEqual(observed, ['complete\n'])
        self.assertEqual(target.read_text(), 'complete\n')
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.assertEqual(list(self.metrics.iterdir()), [target])

    def test_atomic_write_failure_preserves_prior_complete_file_and_cleans_temp(self):
        payloads.write_metrics(self.metrics, 'old\n')
        target = self.metrics / payloads.OUTPUT
        with patch.object(payloads.os, 'replace', side_effect=OSError(errno.EIO, 'fixture')):
            with self.assertRaises(OSError):
                payloads.write_metrics(self.metrics, 'new\n')
        self.assertEqual(target.read_text(), 'old\n')
        self.assertEqual(list(self.metrics.iterdir()), [target])

    def test_cli_fixture_overrides_do_not_execute_payloads(self):
        marker = self.base / 'must-not-exist'
        script = self.root / 'danger.sh'
        script.write_text('#!/bin/sh\ntouch ' + str(marker) + '\n')
        script.chmod(0o755)
        other = self.base / 'second'
        other.mkdir()
        (other / 'another.exe').write_bytes(b'MZ')
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root),
                                 '--root', str(other), '--textfile-dir', str(self.metrics)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists())
        self.assertEqual(result.stdout, '')
        self.assertIn('\nhomelab_download_executable_files 2\n',
                      (self.metrics / payloads.OUTPUT).read_text())

    def test_cli_missing_root_replaces_prior_count_with_failed_metrics(self):
        payloads.write_metrics(self.metrics,
                               payloads.render_metrics(payloads.ScanResult(5, True), 1))
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.base / 'missing'),
                                 '--textfile-dir', str(self.metrics)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        metrics = (self.metrics / payloads.OUTPUT).read_text()
        self.assertIn('\nhomelab_download_payload_scan_success 0\n', metrics)
        self.assertFalse(any(line.startswith('homelab_download_executable_files ')
                             for line in metrics.splitlines()))

    def test_main_metrics_write_failure_returns_nonzero(self):
        with patch.object(payloads, 'scan', return_value=payloads.ScanResult(0, True)), \
                patch.object(payloads, 'write_metrics', side_effect=OSError(errno.EIO, 'fixture')), \
                patch.object(payloads.sys, 'stderr', self.log):
            self.assertEqual(payloads.main(['--textfile-dir', str(self.metrics)]), 1)
        self.assertEqual(self.events()[0]['event'], 'metrics-write-error')

    def test_production_defaults_are_exact_and_not_environment_overrides(self):
        self.assertEqual(payloads.DEFAULT_ROOTS, (Path('/mnt/data/downloads'),
                                                Path('/mnt/pool/downloads'),
                                                Path('/mnt/data/media/downloads')))
        with patch.dict(os.environ, {'TEXTFILE_DIR': '/not-the-production-directory'}):
            args = payloads.parser().parse_args([])
        self.assertIsNone(args.root)
        self.assertEqual(args.textfile_dir, Path('/var/lib/node_exporter/textfile'))


if __name__ == '__main__':
    unittest.main()
