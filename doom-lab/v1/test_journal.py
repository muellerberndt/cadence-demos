"""Small fault-injection tests for journal custody; no server or cloud calls."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

try:
    from . import journal
except ImportError:
    import journal


class SimulatedCrash(BaseException):
    pass


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'online.jsonl'

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def line(n):
        return (json.dumps({'event': 'test', 'n': n}) + '\n').encode()

    def append(self, n, *, limit=4096, segment=60):
        return journal.append_record(self.path, self.line(n),
                                     limit_bytes=limit, segment_bytes=segment)

    def segments(self):
        return sorted(journal.segment_directory(self.path).glob('*.jsonl'))

    def rows(self):
        paths = self.segments() + ([self.path] if self.path.exists() else [])
        return [json.loads(line) for p in paths for line in p.read_bytes().splitlines()]

    def test_threshold_event_is_preserved_and_segments_stay_immutable(self):
        for n in range(3):
            self.assertTrue(self.append(n))
        segment = self.segments()[0]
        frozen = segment.read_bytes()
        self.assertEqual([r['n'] for r in self.rows()], [0, 1, 2])
        self.assertEqual(json.loads(self.path.read_bytes())['n'], 2)
        for n in range(3, 9):
            self.assertTrue(self.append(n))
        self.assertEqual(segment.read_bytes(), frozen)
        self.assertEqual([r['n'] for r in self.rows()], list(range(9)))
        self.assertEqual(journal.usage_bytes(self.path), sum(len(self.line(n)) for n in range(9)))

    def test_crash_before_and_after_rename_preserves_prefix_and_retry(self):
        real_replace = os.replace
        for after in (False, True):
            with self.subTest(after_rename=after):
                self.path = Path(self.tmp.name)/str(after)/'online.jsonl'
                self.path.parent.mkdir()
                self.assertTrue(self.append(0, segment=30))
                def crash(source, destination):
                    if after:
                        real_replace(source, destination)
                    raise SimulatedCrash()
                with patch.object(journal.os, 'replace', side_effect=crash):
                    with self.assertRaises(SimulatedCrash):
                        self.append(1, segment=30)
                self.assertEqual([r['n'] for r in self.rows()], [0])
                self.assertTrue(self.append(1, segment=30))
                self.assertEqual([r['n'] for r in self.rows()], [0, 1])

    def test_incomplete_tail_is_preserved_without_poisoning_readable_prefix(self):
        prefix = self.line(0) + self.line(1)
        broken = prefix + b'{"event":"interrupted"'
        self.path.write_bytes(broken)
        with self.assertRaisesRegex(journal.IncompleteJournalError, 'Incomplete journal tail'):
            self.append(2)
        self.assertEqual(self.path.read_bytes(), broken)
        self.assertEqual([json.loads(line)['n'] for line in broken.splitlines()[:-1]], [0, 1])
        self.assertEqual(self.segments(), [])

    def test_backlog_cap_includes_segments_and_waits_for_external_archive(self):
        length = len(self.line(0))
        for n in range(4):
            self.assertTrue(self.append(n, limit=4*length, segment=2*length))
        before = {p: p.read_bytes() for p in self.segments() + [self.path]}
        self.assertFalse(self.append(4, limit=4*length, segment=2*length))
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        # The archive owner verifies and removes a closed segment separately.
        archived = self.segments()[0]
        archived_bytes = archived.read_bytes()
        archived.unlink()
        self.assertTrue(self.append(4, limit=4*length, segment=2*length))
        retained = [json.loads(line) for line in archived_bytes.splitlines()] + self.rows()
        self.assertEqual([r['n'] for r in retained], list(range(5)))

    def test_preexisting_large_active_file_rotates_without_loss(self):
        self.path.write_bytes(b''.join(self.line(n) for n in range(5)))
        self.assertTrue(self.append(5))
        self.assertEqual([r['n'] for r in self.rows()], list(range(6)))
        self.assertEqual(len(self.segments()), 1)

    def test_single_large_event_is_not_split_but_cannot_exceed_cap(self):
        line = json.dumps({'event': 'snapshot', 'data': 'x'*400}).encode() + b'\n'
        self.assertTrue(journal.append_record(self.path, line, limit_bytes=1024, segment_bytes=60))
        self.assertEqual(self.path.read_bytes(), line)
        self.assertTrue(self.append(1, limit=1024))
        self.assertEqual(self.segments()[0].read_bytes(), line)
        before = journal.usage_bytes(self.path)
        self.assertFalse(journal.append_record(self.path, line, limit_bytes=before, segment_bytes=60))
        self.assertEqual(journal.usage_bytes(self.path), before)

    def test_external_lock_serializes_multiple_event_sources(self):
        lock = threading.Lock()
        def append(n):
            with lock:
                return self.append(n)
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(append, range(32))))
        self.assertEqual(sorted(r['n'] for r in self.rows()), list(range(32)))


if __name__ == '__main__':
    unittest.main()
