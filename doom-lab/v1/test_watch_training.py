"""Monitor boundaries, failure reporting and non-inference of competence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

try:
    from . import watch_training as monitor
except ImportError:
    import watch_training as monitor


class MonitorTests(unittest.TestCase):
    def test_only_small_metadata_is_read_and_payloads_are_omitted(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            run = base/'runs/teacher_probe_01/e1m1_full_01'; run.mkdir(parents=True)
            (run/'summary.json').write_text(json.dumps({'schema': 'doom-v3-teacher-result/1',
                'outcome': {'success': False, 'timeout': True, 'killcount': 4},
                'snapshot': 'must not transfer', 'gates': [{'task_id': 'e1m1', 'scope': 'teacher', 'passed': False}]}))
            (run/'decisions.jsonl').write_text('not even JSON')
            (run/'status.json').write_text('{incomplete')
            (run/'freeze.json').write_text('x'*(1024*1024+1))
            result = monitor.collect_remote(base)
        self.assertEqual(len(result['runs']), 1)
        row = result['runs'][0]
        self.assertEqual(row['run'], 'teacher_probe_01/e1m1_full_01')
        self.assertNotIn('snapshot', row['files']['summary.json'])
        self.assertNotIn('decisions.jsonl', row['files'])
        self.assertEqual(len(row['errors']), 2)
        self.assertLess(len(json.dumps(result)), 192*1024)

    def test_success_counts_do_not_create_student_gates(self):
        remote = {'checked_unix': 100, 'base_exists': True, 'resources': {}, 'runs': [
            {'run': 'teacher_probe', 'files': {'summary.json': {'successes': 10, 'scheduled': 10,
                 'outcome': {'success': True, 'native_exit': True}}}}]}
        data = monitor.combine(remote, {}, host='example', now=101)
        self.assertEqual(data['task_gates'], [])
        self.assertEqual(data['phase'], 'full_game_development')
        self.assertNotIn('competent', data)

    def test_declared_teacher_gates_retain_scope_and_provenance(self):
        rows = [{'run': 'teacher_probe/e1m1', 'files': {'summary.json': {
            'gates': [{'task_id': 'e1m1', 'scope': 'teacher', 'passed': True}]}}}]
        gates = monitor.declared_gates(rows)
        self.assertEqual(gates[0]['scope'], 'teacher')
        self.assertEqual(gates[0]['source_run'], 'teacher_probe/e1m1')

    def test_cpu_rate_uses_successive_counters_and_reboot_does_not_invent_usage(self):
        old = {'resources': {'cpu_ticks': {'total': 100, 'idle': 40}}}
        remote = {'checked_unix': 100, 'base_exists': True, 'runs': [],
                  'resources': {'cpu_ticks': {'total': 200, 'idle': 60}}}
        self.assertEqual(monitor.combine(remote, old, host='example')['resources']['cpu_utilization_percent'], 80)
        remote['resources']['cpu_ticks'] = {'total': 10, 'idle': 4}
        self.assertIsNone(monitor.combine(remote, old, host='example')['resources']['cpu_utilization_percent'])

    def test_ssh_is_read_only_and_timeout_bounded(self):
        response = Mock(stdout='{"runs":[],"resources":{}}')
        with patch.object(monitor.subprocess, 'run', return_value=response) as run:
            monitor.read_remote('example.test', Path('/private/key'), '/home/ec2-user/doom-v3')
        args, kwargs = run.call_args
        self.assertEqual(args[0][-1], 'python3 -')
        self.assertEqual(kwargs['timeout'], 25)
        self.assertIn('collect_remote', kwargs['input'])
        self.assertNotIn('write_text', kwargs['input'])
        self.assertNotIn('unlink', kwargs['input'])
        with self.assertRaises(ValueError):
            monitor.read_remote('bad;host', Path('/private/key'), '/tmp')

    def test_local_health_uses_only_get_state_not_keyboard_websocket(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({'mode': 'teach', 'model': {'id': 'legacy'}, 'learning': {}}).encode()
        with patch.object(monitor.urllib.request, 'urlopen', return_value=response) as opened:
            result = monitor.local_actor('http://localhost:8666')
        self.assertEqual(opened.call_args.args[0], 'http://localhost:8666/state')
        self.assertEqual(result['mode'], 'teach')

    def test_atomic_status_size_cap_preserves_previous_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'status.json'
            monitor.atomic_json(path, {'previous': True})
            with self.assertRaises(ValueError):
                monitor.atomic_json(path, {'large': 'x'*monitor.MAX_STATUS_BYTES})
            self.assertEqual(json.loads(path.read_text()), {'previous': True})

    def test_same_host_monitor_does_not_use_ssh_or_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = {'checked_unix': 100, 'base_exists': True, 'resources': {}, 'runs': []}
            argv = ['monitor', '--local-base', directory, '--once', '--url', 'http://127.0.0.1:8667',
                    '--output', str(root/'status.json'), '--receipt', str(root/'process.json')]
            with patch('sys.argv', argv), patch.object(monitor, 'collect_remote', return_value=remote) as local:
                with patch.object(monitor, 'read_remote') as ssh, patch.object(monitor, 'local_actor', return_value={'mode': 'idle'}):
                    monitor.main()
            local.assert_called_once_with(directory)
            ssh.assert_not_called()
            self.assertEqual(json.loads((root/'process.json').read_text())['transport'], 'same_host_read_only')


if __name__ == '__main__':
    unittest.main()
