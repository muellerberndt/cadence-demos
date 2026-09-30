"""Bounded, durable JSONL segments for one externally serialized journal writer.

The caller holds its journal lock across ``append_record``. Published segments
are never modified here. An archive process may remove a segment only after
verifying its remote bytes; it must never rename, truncate or remove the active
journal. Only remaining local bytes count against the backlog cap.
"""
from __future__ import annotations

import os
from pathlib import Path
import time
import uuid


SEGMENT_BYTES = 8 * 1024 * 1024


class IncompleteJournalError(OSError):
    """Preserve an interrupted last record for explicit recovery; never join it."""


def segment_directory(path):
    return Path(path).parent / (Path(path).stem + '_segments')


def _size(path):
    try:
        return path.stat().st_size
    except FileNotFoundError:
        # The uploader may have just removed a verified, immutable segment.
        return 0


def usage_bytes(path):
    """Conservative local backlog size; archive deletion can race this read."""
    path = Path(path)
    return _size(path) + sum(_size(p) for p in segment_directory(path).glob('*.jsonl'))


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _complete_tail(path, size):
    if size:
        with path.open('rb') as stream:
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b'\n':
                raise IncompleteJournalError(
                    f'Incomplete journal tail preserved in {path}; recover before restarting')


def _rotate(path):
    directory = segment_directory(path)
    if not directory.exists():
        directory.mkdir()
        _sync_directory(path.parent)
    # Flush the source before publishing its immutable name. A crash before
    # rename leaves the active file; after rename the same prefix is a segment.
    with path.open('rb') as stream:
        os.fsync(stream.fileno())
    destination = directory / f'{time.time_ns():020d}-{uuid.uuid4().hex}.jsonl'
    while destination.exists():
        destination = directory / f'{time.time_ns():020d}-{uuid.uuid4().hex}.jsonl'
    os.replace(path, destination)
    _sync_directory(directory)
    _sync_directory(path.parent)


def append_record(path, line, *, limit_bytes, segment_bytes=SEGMENT_BYTES):
    """Fsync one whole event, returning False without mutation if backlog is full.

    Rotation precedes a threshold-crossing event, so that event remains in the
    new active file. A single event larger than the segment target is allowed
    only within the aggregate cap and is never split. Interrupted partial tails
    are refused intact; a return of True is the acknowledgement of durable bytes.
    """
    if not isinstance(line, bytes) or not line.endswith(b'\n') or b'\n' in line[:-1]:
        raise ValueError('Expected one newline-terminated JSONL record as bytes')
    if limit_bytes <= 0 or segment_bytes <= 0:
        raise ValueError('Journal limits must be positive')
    path = Path(path)
    size = _size(path)
    _complete_tail(path, size)
    if usage_bytes(path) + len(line) > limit_bytes:
        return False
    if size and size + len(line) > segment_bytes:
        _rotate(path)
    created = not path.exists()
    with path.open('ab') as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    if created:
        _sync_directory(path.parent)
    return True
