"""Bounded read-only cloud monitoring for full-game development, not promotion.

Only small JSON status/freeze/summary files cross SSH. No model, corpus, raw log,
cloud resource, or live actor is changed. A static JSON file feeds the existing UI.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
WORKSPACE = LAB.parents[1]
DEFAULT_OUTPUT = LAB/'static/training_status.json'
MAX_STATUS_BYTES = 384*1024

# This same function is sent to the host and exercised against fixture directories.
def collect_remote(base):
    import json, os, pathlib, shutil, subprocess, time
    base = pathlib.Path(base)
    root = base/'runs'
    names = ('status.json', 'summary.json', 'receipt.json', 'failure.json',
             'freeze.json', 'supervisor.json', 'launch.json', 'gate.json', 'gates.json')
    omit = {'snapshot', 'weights', 'biases', 'inputs', 'labels', 'admissions',
            'champion', 'contexts', 'engine', 'environment', 'source_hashes',
            'implementation', 'images', 'observations', 'decisions'}
    def compact(value, depth=0):
        if depth > 5:
            return '<depth limit>'
        if isinstance(value, str):
            return value[:1200]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, dict):
            result = {}
            for k, v in list(value.items())[:80]:
                if k in omit:
                    continue
                if k == 'gates' and isinstance(v, list):
                    # Full per-update gate trajectories are bulk evidence. Only
                    # explicit named task-gate declarations belong in this UI.
                    v = [g for g in v if isinstance(g, dict) and 'task_id' in g]
                result[str(k)[:100]] = compact(v, depth+1)
            return result
        if isinstance(value, list):
            return [compact(v, depth+1) for v in value[:24]]
        return str(value)[:100]
    disk = shutil.disk_usage(base if base.exists() else base.parent)
    resources = {'cpus': os.cpu_count(), 'load': list(os.getloadavg()),
                 'disk_total_bytes': disk.total, 'disk_free_bytes': disk.free}
    mem = pathlib.Path('/proc/meminfo')
    if mem.exists():
        for line in mem.read_text().splitlines():
            key = line.split(':', 1)[0]
            if key in ('MemTotal', 'MemAvailable'):
                resources[{'MemTotal': 'memory_total_bytes', 'MemAvailable': 'memory_available_bytes'}[key]] = int(line.split()[1])*1024
    stat = pathlib.Path('/proc/stat')
    if stat.exists():
        values = [int(v) for v in stat.read_text().splitlines()[0].split()[1:]]
        resources['cpu_ticks'] = {'total': sum(values[:8]), 'idle': values[3]+values[4]}
    processes = []
    try:
        text = subprocess.run(['ps', '-eo', 'pid,etime,pcpu,pmem,args'],
                              capture_output=True, text=True, timeout=5, check=True).stdout
        for line in text.splitlines()[1:]:
            values = line.split(None, 4)
            if len(values) == 5 and ('/doom-v3-' in values[4] or re_marker(values[4])):
                processes.append({'pid': int(values[0]), 'elapsed': values[1],
                                  'cpu_percent_lifetime': float(values[2]),
                                  'memory_percent': float(values[3]), 'command': values[4][:320]})
    except Exception as error:
        resources['process_read_error'] = str(error)[:200]
    resources['processes'] = processes[:24]
    result = {'checked_unix': time.time(), 'base_exists': base.is_dir(),
              'runs': [], 'resources': resources, 'scan_errors': []}
    if not root.exists():
        return result
    folders, frontier = [], [(root, 0)]
    while frontier and len(folders) < 80:
        parent, depth = frontier.pop(0)
        for folder in sorted(parent.iterdir()):
            if not folder.is_dir() or folder.is_symlink() or folder.name in ('exports', 'sources', 'checkpoints'):
                continue
            folders.append(folder)
            if depth < 2:
                frontier.append((folder, depth+1))
            if len(folders) >= 80:
                break
    for folder in folders:
        row = {'run': str(folder.relative_to(root)), 'files': {}, 'errors': [], 'modified_unix': 0}
        for name in names:
            path = folder/name
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                info = path.stat()
                row['modified_unix'] = max(row['modified_unix'], info.st_mtime)
                if info.st_size > 1024*1024:
                    row['errors'].append(name+': exceeds 1MiB metadata limit')
                    continue
                row['files'][name] = compact(json.loads(path.read_text()))
            except (OSError, ValueError) as error:
                row['errors'].append(name+': '+str(error)[:180])
        if not row['files'] and not row['errors']:
            continue
        if len(json.dumps(row)) > 48*1024:
            row['files'] = {name: {k: v for k, v in value.items() if not isinstance(v, (dict, list))}
                            for name, value in row['files'].items() if isinstance(value, dict)}
            row['errors'].append('Nested metadata omitted to preserve the 48KiB row bound')
        result['runs'].append(row)
        if len(json.dumps(result)) > 192*1024:
            result['runs'].pop()
            result['scan_errors'].append('Additional metadata omitted to preserve the 192KiB transfer bound')
            break
    return result


def re_marker(command):
    return any(marker in command for marker in ('-m v1.', '/v1/', '-m v3.', '/v3/'))


def atomic_json(path, value):
    payload = json.dumps(value, separators=(',', ':'), allow_nan=False)+'\n'
    if len(payload.encode()) > MAX_STATUS_BYTES:
        raise ValueError('Monitor status exceeds the local bounded output limit')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.'+path.name,
                                          suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def read_remote(host, key, base):
    import inspect
    if not re.fullmatch(r'[A-Za-z0-9.-]+', host):
        raise ValueError('Invalid SSH host')
    code = inspect.getsource(re_marker)+'\n'+inspect.getsource(collect_remote)
    code += '\nimport json\nprint(json.dumps(collect_remote('+repr(base)+'),allow_nan=False))\n'
    command = ['ssh', '-i', str(key), '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
               '-o', 'StrictHostKeyChecking=accept-new', 'ec2-user@'+host, 'python3 -']
    result = subprocess.run(command, input=code, capture_output=True, text=True,
                            timeout=25, check=True)
    if len(result.stdout.encode()) > 256*1024:
        raise ValueError('Remote monitor response exceeded the transfer limit')
    return json.loads(result.stdout)


def local_actor(url):
    with urllib.request.urlopen(url.rstrip('/')+'/state', timeout=4) as response:
        data = json.loads(response.read(256*1024))
    model, learning = data.get('model', {}), data.get('learning', {})
    return {'checked_unix': time.time(), 'model_id': model.get('id'),
            'scenario': model.get('scenario'), 'champion': learning.get('champion'),
            'mode': data.get('mode'), 'episode': data.get('episode'),
            'learning_enabled': learning.get('enabled'),
            'accepted_updates': learning.get('accepted_updates'),
            'checkpoint_sha256': learning.get('champion_sha256'),
            'error': model.get('error') or learning.get('error')}


def declared_gates(runs):
    gates = []
    for run in runs:
        for filename, value in run.get('files', {}).items():
            if not isinstance(value, dict):
                continue
            records = value.get('gates', [])
            if isinstance(records, dict):
                records = [dict(v, task_id=k) for k, v in records.items() if isinstance(v, dict)]
            if filename == 'gate.json':
                records = [value]
            for gate in records if isinstance(records, list) else []:
                if (isinstance(gate, dict) and isinstance(gate.get('task_id'), str)
                        and type(gate.get('passed')) is bool):
                    gates.append({**gate, 'scope': gate.get('scope', 'unspecified'),
                                  'source_run': run['run'], 'source_file': filename})
    return gates[:60]


def combine(remote, previous, *, host, actor=None, now=None):
    now = time.time() if now is None else now
    resources = remote['resources']
    current = resources.get('cpu_ticks', {})
    old = (previous or {}).get('resources', {}).get('cpu_ticks', {})
    total, idle = current.get('total', 0)-old.get('total', 0), current.get('idle', 0)-old.get('idle', 0)
    resources['cpu_utilization_percent'] = max(0, min(100, 100*(1-idle/total))) if old and total > 0 and idle >= 0 else None
    return {'schema': 'doom-v3-training-monitor/1', 'updated_unix': now,
            'last_cloud_update_unix': remote['checked_unix'], 'remote_host': host,
            'cloud_state': 'reachable', 'phase': 'full_game_development',
            'monitor_state': 'running', 'resources': resources,
            'runs': remote['runs'], 'scan_errors': remote.get('scan_errors', []),
            'base_exists': remote['base_exists'], 'task_gates': declared_gates(remote['runs']),
            'browser_actor': actor, 'error': None,
            'interpretation': 'Development status only. Basic actor, teacher probes and student task gates are distinct; no claim of full-game competence.'}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--host', default='100.31.68.116')
    result.add_argument('--remote-base', default='/home/ec2-user/doom-v3-20260929')
    result.add_argument('--local-base', type=Path,
                        help='Read this same-host campaign directory directly; no SSH/key is used')
    result.add_argument('--key', type=Path, default=WORKSPACE/'credentials/Cadence1.pem')
    result.add_argument('--interval', type=float, default=15)
    result.add_argument('--hours', type=float, default=8)
    result.add_argument('--once', action='store_true')
    result.add_argument('--url', default='http://127.0.0.1:8666')
    result.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    result.add_argument('--receipt', type=Path, default=HERE/'ops/monitor_process.json')
    return result


def main():
    args = parser().parse_args()
    if not all(math.isfinite(value) and value > 0 for value in (args.interval, args.hours)):
        raise ValueError('Poll interval and lifetime must be positive finite values')
    started = time.time(); expires = started+args.hours*3600
    process = {'schema': 'doom-v3-monitor-process/1', 'pid': os.getpid(), 'started_unix': started,
               'expires_unix': expires, 'host': args.host, 'remote_base': args.remote_base,
               'local_base': str(args.local_base) if args.local_base else None,
               'transport': 'same_host_read_only' if args.local_base else 'ssh_read_only',
               'interval_seconds': args.interval, 'hours': args.hours, 'output': str(args.output),
               'read_only_cloud': True, 'state': 'running'}
    atomic_json(args.receipt, process)
    previous = json.loads(args.output.read_text()) if args.output.exists() else {}
    while True:
        local_error = None
        try:
            actor = local_actor(args.url)
        except Exception as error:
            actor = previous.get('browser_actor')
            local_error = str(error)[:500]
        try:
            remote = collect_remote(str(args.local_base)) if args.local_base else read_remote(args.host, args.key, args.remote_base)
            status = combine(remote, previous, host=args.host, actor=actor)
        except Exception as error:
            status = {**previous, 'schema': 'doom-v3-training-monitor/1',
                      'updated_unix': time.time(), 'remote_host': args.host,
                      'cloud_state': 'unknown', 'monitor_state': 'running',
                      'phase': 'full_game_development', 'browser_actor': actor,
                      'error': (getattr(error, 'stderr', None) or str(error))[:1200]}
        status.update(monitor_expires_unix=expires, local_error=local_error)
        finished = args.once or time.time() >= expires
        if finished:
            status['monitor_state'] = 'once_complete' if args.once else 'expired'
        atomic_json(args.output, status)
        print(json.dumps({'unix': time.time(), 'cloud_state': status['cloud_state'],
                          'runs': len(status.get('runs', [])), 'error': status.get('error')}), flush=True)
        previous = status
        if finished:
            process.update(state=status['monitor_state'], finished_unix=time.time())
            atomic_json(args.receipt, process)
            break
        time.sleep(min(args.interval, max(0, expires-time.time())))


if __name__ == '__main__':
    main()
