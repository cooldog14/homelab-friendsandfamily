#!/usr/bin/env python3
"""Detect executable download payloads without following links or opening archives."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
from typing import TextIO


DEFAULT_ROOTS = (
    Path('/mnt/data/downloads'),
    Path('/mnt/pool/downloads'),
    Path('/mnt/data/media/downloads'),
)
DEFAULT_TEXTFILE_DIR = Path('/var/lib/node_exporter/textfile')
OUTPUT = 'homelab-download-payloads.prom'
EXECUTABLE_SUFFIXES = frozenset({
    '.exe', '.dll', '.com', '.scr', '.msi', '.bat', '.cmd', '.ps1',
    '.vbs', '.js', '.jar', '.sh', '.appimage',
})
MACH_O_MAGICS = frozenset({
    b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe',
    b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe',
    b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
    b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca',
})
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


@dataclass(frozen=True)
class ScanResult:
    executable_files: int
    success: bool


def classify(name: str, header: bytes) -> list[str]:
    classifications = []
    suffix = Path(name).suffix.lower()
    if suffix in EXECUTABLE_SUFFIXES:
        classifications.append('suffix:' + suffix)
    if header.startswith(b'\x7fELF'):
        classifications.append('header:ELF')
    elif header.startswith(b'MZ'):
        classifications.append('header:MZ')
    elif header in MACH_O_MAGICS:
        classifications.append('header:Mach-O')
    return classifications


def journal(stream: TextIO, event: str, path: Path, **fields: object) -> None:
    # JSON escapes newlines, controls, undecodable names and journal-like prefixes.
    # File contents and raw exception messages never enter the journal or metrics.
    print(json.dumps({'event': event, 'path': str(path), **fields},
                     ensure_ascii=True, sort_keys=True), file=stream)


def open_root(root: Path) -> int:
    """Open every root component without following ancestor symlinks either."""
    fd = os.open(root.anchor or '.', DIRECTORY_FLAGS)
    try:
        components = root.parts[1:] if root.anchor else root.parts
        for component in components:
            child_fd = os.open(component, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child_fd
        return fd
    except OSError:
        os.close(fd)
        raise


def scan(roots: tuple[Path, ...], stream: TextIO = sys.stderr) -> ScanResult:
    headers: dict[tuple[int, int], bytes] = {}
    detected: set[tuple[int, int]] = set()
    seen_directories: set[tuple[int, int]] = set()
    count = 0
    success = True

    def failed(path: Path, error: OSError) -> None:
        nonlocal success
        success = False
        journal(stream, 'scan-error', path, errno=error.errno)

    def enter(fd: int, path: Path, stack: list) -> None:
        try:
            identity = os.fstat(fd)
            key = (identity.st_dev, identity.st_ino)
            if key in seen_directories:
                os.close(fd)
                return
            entries = os.scandir(fd)
            seen_directories.add(key)
            stack.append((fd, path, entries))
        except OSError as error:
            os.close(fd)
            failed(path, error)

    for root in roots:
        try:
            fd = open_root(root)
        except OSError as error:
            # A missing or symlinked root is not an empty successful scan.
            failed(root, error)
            continue
        stack: list = []
        enter(fd, root, stack)
        try:
            while stack:
                directory_fd, directory, entries = stack[-1]
                try:
                    entry = next(entries)
                except (StopIteration, OSError) as error:
                    if isinstance(error, OSError):
                        failed(directory, error)
                    entries.close()
                    os.close(directory_fd)
                    stack.pop()
                    continue
                path = directory / entry.name
                try:
                    metadata = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(metadata.st_mode):
                        child_fd = os.open(entry.name, DIRECTORY_FLAGS,
                                           dir_fd=directory_fd)
                        enter(child_fd, path, stack)
                        continue
                    if not stat.S_ISREG(metadata.st_mode):
                        continue
                    key = (metadata.st_dev, metadata.st_ino)
                    if key not in headers:
                        file_fd = os.open(entry.name, FILE_FLAGS, dir_fd=directory_fd)
                        try:
                            # Recheck after open: a concurrent rename cannot trick us
                            # into reading a symlink target, FIFO or device.
                            opened = os.fstat(file_fd)
                            if not stat.S_ISREG(opened.st_mode):
                                continue
                            key = (opened.st_dev, opened.st_ino)
                            if key not in headers:
                                headers[key] = os.read(file_fd, 4)
                        finally:
                            os.close(file_fd)
                    classifications = classify(entry.name, headers[key])
                    if classifications and key not in detected:
                        detected.add(key)
                        count += 1
                        journal(stream, 'executable-payload', path,
                                classification=classifications)
                except FileNotFoundError:
                    # Downloads may be moved/deleted while the timer is scanning.
                    continue
                except OSError as error:
                    if error.errno == errno.ELOOP:
                        # Replaced by a symlink after stat; never follow it.
                        continue
                    failed(path, error)
        finally:
            for directory_fd, _, entries in reversed(stack):
                entries.close()
                os.close(directory_fd)
    return ScanResult(count, success)


def render_metrics(result: ScanResult, timestamp: int) -> str:
    lines = [
        '# HELP homelab_download_executable_files Executable payload files in a complete scan.',
        '# TYPE homelab_download_executable_files gauge',
    ]
    # A failed/partial scan replaces the previous file but omits the count, even
    # if some payloads were found. Neither a false zero nor retained evidence.
    if result.success:
        lines.append(f'homelab_download_executable_files {result.executable_files}')
    lines.extend([
        '# HELP homelab_download_payload_scan_success Whether the latest scan completed without errors.',
        '# TYPE homelab_download_payload_scan_success gauge',
        f'homelab_download_payload_scan_success {int(result.success)}',
        '# HELP homelab_download_payload_scan_timestamp_seconds Completion time of the latest scan attempt.',
        '# TYPE homelab_download_payload_scan_timestamp_seconds gauge',
        f'homelab_download_payload_scan_timestamp_seconds {timestamp}',
    ])
    return '\n'.join(lines) + '\n'


def write_metrics(directory: Path, metrics: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.homelab-download-payloads.', suffix='.tmp',
                                     dir=directory)
    try:
        with os.fdopen(fd, 'w') as output:
            os.fchmod(output.fileno(), 0o644)
            output.write(metrics)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, directory / OUTPUT)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--root', type=Path, action='append',
                        help='Scan this root instead of the production roots (repeatable).')
    result.add_argument('--textfile-dir', type=Path, default=DEFAULT_TEXTFILE_DIR,
                        help='Directory for the atomic node-exporter metrics file.')
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    result = scan(tuple(args.root) if args.root else DEFAULT_ROOTS)
    try:
        write_metrics(args.textfile_dir, render_metrics(result, int(time.time())))
    except OSError as error:
        journal(sys.stderr, 'metrics-write-error', args.textfile_dir, errno=error.errno)
        return 1
    return 0 if result.success else 1


if __name__ == '__main__':
    raise SystemExit(main())
